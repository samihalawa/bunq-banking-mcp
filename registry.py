"""Pinned official bunq operation catalog and strict, account-bound request preparation."""
from __future__ import annotations
import base64
import binascii
import copy
import json
import re
from pathlib import Path
from jsonschema import Draft7Validator, RefResolver

METHODS = {'get', 'post', 'put', 'patch', 'delete'}
PAGINATION = {
    'count': {'type': 'integer', 'minimum': 1, 'maximum': 200},
    'older_id': {'type': 'integer', 'minimum': 0},
    'newer_id': {'type': 'integer', 'minimum': 0},
}
SECRET_SEGMENTS = {'installation', 'device-server', 'session-server', 'session',
                   'api-key', 'credential-password-ip', 'certificate-pinned',
                   'payment-service-provider-credential', 'oauth-client',
                   'generated-cvc2', 'card-cvc2'}
SAFE_WRITES = {'note-text', 'note-attachment', 'notification-filter-email',
               'notification-filter-failure', 'notification-filter-push',
               'notification-filter-url', 'additional-transaction-information-category-user-defined',
               'customer-statement', 'export-annual-overview', 'export-rib',
               'export-statement-card-csv', 'export-statement-card-pdf',
               'invoice-export', 'statement', 'avatar', 'company',
               'user-company', 'user-person', 'confirmation-of-funds',
               'attachment', 'attachment-public'}
MONEY_MARKERS = ('payment', 'request-response', 'request-inquiry', 'schedule',
                 'transferwise', 'currency-conversion', 'currency-cloud',
                 'whitelist', 'transaction', 'bunqme', 'token-qr', 'share-invite',
                 'monetary-account', 'card', 'challenge-request', 'replace')

MAX_UPLOAD_BYTES = 10 * 1024 * 1024
UPLOAD_SCHEMA = {
    'type': 'object',
    'properties': {
        'data_base64': {'type': 'string', 'minLength': 4, 'maxLength': ((MAX_UPLOAD_BYTES + 2) // 3) * 4},
        'content_type': {'type': 'string', 'enum': ['image/png', 'image/jpeg', 'image/gif']},
        'description': {'type': 'string', 'minLength': 1, 'maxLength': 140, 'pattern': r'^[^\r\n]+$'},
    },
    'required': ['data_base64', 'content_type', 'description'],
    'additionalProperties': False,
}


def _request_schemas(value):
    """OpenAPI request direction and strict unknown-property checks, preserving refs."""
    if isinstance(value, list):
        return [_request_schemas(v) for v in value]
    if not isinstance(value, dict):
        return value
    out = {k: _request_schemas(v) for k, v in value.items()}
    if out.get('type') == 'object' or 'properties' in out:
        props = out.get('properties', {})
        removed = {k for k, v in props.items() if v.get('readOnly')}
        out['properties'] = {k: v for k, v in props.items() if k not in removed}
        out['additionalProperties'] = False
        if 'required' in out:
            out['required'] = [k for k in out['required'] if k not in removed]
    # OpenAPI 3.0 nullable is not understood by JSON Schema draft 7.
    if out.pop('nullable', False) and isinstance(out.get('type'), str):
        out['type'] = [out['type'], 'null']
    return out


class Registry:
    def __init__(self, spec_path=None):
        self.spec_path = Path(spec_path or Path(__file__).with_name('openapi.json'))
        self.spec = json.loads(self.spec_path.read_text())
        self.validation_spec = copy.deepcopy(self.spec)
        self.validation_spec['components']['schemas'] = _request_schemas(self.spec['components']['schemas'])
        self.resolver = RefResolver.from_schema(self.validation_spec)
        self.operations = {}
        for path, path_item in self.spec['paths'].items():
            for method, op in path_item.items():
                if method not in METHODS:
                    continue
                name = op['operationId']
                if name in self.operations:
                    raise ValueError(f'Duplicate operationId: {name}')
                params = [self._resolve(p) for p in path_item.get('parameters', []) + op.get('parameters', [])]
                body = self._resolve(op.get('requestBody', {}))
                content = body.get('content', {})
                schema = content.get('application/json', {}).get('schema')
                resource = next(s for s in reversed(path.split('/')) if s and not s.startswith('{'))
                binary_upload = method == 'post' and resource in {'attachment', 'attachment-public'}
                reason = self._disabled_reason(path, method, content, schema)
                if binary_upload:
                    schema = copy.deepcopy(UPLOAD_SCHEMA)
                self.operations[name] = {
                    'name': name, 'method': method.upper(), 'path': path,
                    'category': (op.get('tags') or ['other'])[0],
                    'description': op.get('description') or op.get('summary') or '',
                    'available': reason is None, 'unavailable_reason': reason,
                    'parameters': params, 'body_schema': schema, 'binary_upload': binary_upload,
                    'body_required': binary_upload or body.get('required', False),
                    'output_schema': self._resolve(op.get('responses', {}).get('200', {})).get('content', {}).get('application/json', {}).get('schema'),
                    'response_content_types': sorted({t for r in op.get('responses', {}).values()
                                                      for t in self._resolve(r).get('content', {})}),
                }

    def _resolve(self, obj):
        while isinstance(obj, dict) and '$ref' in obj:
            ref = obj['$ref']
            if not ref.startswith('#/'):
                raise ValueError('External schema references are unsupported')
            obj = self.spec
            for key in ref[2:].split('/'):
                obj = obj[key.replace('~1', '/').replace('~0', '~')]
        return obj

    def _disabled_reason(self, path, method, content, schema):
        segments = {s for s in path.split('/') if s and not s.startswith('{')}
        if segments & SECRET_SEGMENTS:
            return 'Authentication, credential and session operations are private to the transport.'
        if any(s.startswith('sandbox-') for s in segments) or 'server-error' in segments:
            return 'Sandbox/bootstrap/debug endpoint is outside this production account integration.'
        if method == 'get':
            return None
        resource = next(s for s in reversed(path.split('/')) if s and not s.startswith('{'))
        if content and ('application/json' not in content or schema is None):
            return 'Non-JSON request body is not implemented.'
        if resource in SAFE_WRITES:
            return None
        if any(marker in resource for marker in MONEY_MARKERS):
            return 'Money movement, payment authorization, trading, fee-bearing creation or financial automation is disabled by owner instruction.'
        return 'Mutation requires a reviewed nonfinancial operation classification before execution.'

    def catalog(self, search='', category=None, cursor=0, limit=30):
        if isinstance(cursor, bool) or not isinstance(cursor, int) or cursor < 0:
            raise ValueError('cursor must be a nonnegative integer')
        if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 100:
            raise ValueError('limit must be between 1 and 100')
        if not isinstance(search, str) or (category is not None and not isinstance(category, str)):
            raise ValueError('search/category must be text')
        rows = [self._summary(o) for o in self.operations.values()
                if (not category or o['category'] == category)
                and search.casefold() in (' '.join((o['name'], o['path'], o['description']))).casefold()]
        rows.sort(key=lambda o: o['name'])
        return {'total': len(rows), 'operations': rows[cursor:cursor + limit],
                'next_cursor': cursor + limit if cursor + limit < len(rows) else None,
                'categories': sorted({o['category'] for o in self.operations.values()})}

    @staticmethod
    def _summary(op):
        return {k: op[k] for k in ('name', 'method', 'path', 'category', 'available', 'unavailable_reason')}

    def learn(self, names):
        if isinstance(names, str):
            names = [names]
        if not isinstance(names, list) or not 1 <= len(names) <= 20:
            raise ValueError('names must contain 1 to 20 operation names')
        result = []
        for name in names:
            op = self._get(name)
            path_props = {p['name']: p.get('schema', {}) for p in op['parameters']
                          if p['in'] == 'path' and p['name'] != 'userID'}
            query_props = {p['name']: p.get('schema', {}) for p in op['parameters'] if p['in'] == 'query'}
            if op['method'] == 'GET' and op['name'].startswith('List_all_'):
                query_props.update(PAGINATION)
            input_props = {
                'path': {'type': 'object', 'properties': path_props,
                         'required': [p['name'] for p in op['parameters'] if p['in'] == 'path' and p['name'] != 'userID'],
                         'additionalProperties': False},
                'query': {'type': 'object', 'properties': query_props, 'additionalProperties': False},
            }
            input_required = ['path'] if input_props['path']['required'] else []
            if op['body_schema']:
                input_props['body'] = _request_schemas(op['body_schema'])
                if op['body_required']:
                    input_required.append('body')
            definitions = self._definitions(op['body_schema'])
            input_schema = {'type': 'object', 'properties': input_props, 'required': input_required,
                            'additionalProperties': False, 'components': {'schemas': definitions}}
            result.append({**copy.deepcopy(op), 'input_schema': input_schema,
                'output_schema_document': {'schema': op['output_schema'], 'components': {'schemas': self._definitions(op['output_schema'], request=False)}},
                'annotations': {'readOnlyHint': op['method'] == 'GET',
                                'destructiveHint': op['method'] != 'GET',
                                'idempotentHint': op['method'] in {'GET', 'PUT', 'DELETE'},
                                'openWorldHint': True}, 'arguments': {
                'path': path_props, 'query': query_props, 'body': op['body_schema']},
                'schema_definitions': self._definitions(op['body_schema']),
                'user_binding': 'userID is supplied by authenticated session; callers cannot choose it.'})
        return result

    def _definitions(self, schema, request=True):
        definitions = {}
        def visit(value):
            if isinstance(value, list):
                for child in value:
                    visit(child)
            elif isinstance(value, dict):
                ref = value.get('$ref', '')
                if ref.startswith('#/components/schemas/'):
                    key = ref.rsplit('/', 1)[-1]
                    if key not in definitions:
                        source = self.validation_spec if request else self.spec
                        definitions[key] = source['components']['schemas'][key]
                        visit(definitions[key])
                for key, child in value.items():
                    if key != '$ref':
                        visit(child)
        visit(schema)
        return copy.deepcopy(definitions)

    def _get(self, name):
        if not isinstance(name, str) or name not in self.operations:
            raise ValueError(f'Unknown official operation: {name}')
        return self.operations[name]

    def _validate(self, instance, schema, label):
        errors = sorted(Draft7Validator(schema, resolver=self.resolver).iter_errors(instance), key=lambda e: str(e.path))
        if errors:
            e = errors[0]
            location = '.'.join(map(str, e.path))
            raise ValueError(f'{label}{"." + location if location else ""}: {e.message}')

    def prepare(self, name, arguments, user_id):
        op = self._get(name)
        if not op['available']:
            raise ValueError(op['unavailable_reason'])
        if not isinstance(arguments, dict) or set(arguments) - {'path', 'query', 'body'}:
            raise ValueError('arguments allows only path, query and body')
        paths = arguments.get('path', {})
        query = arguments.get('query', {})
        if not isinstance(paths, dict) or not isinstance(query, dict):
            raise ValueError('path and query must be objects')
        expected = {p['name']: p for p in op['parameters'] if p['in'] == 'path'}
        if 'userID' in paths:
            raise ValueError('userID is bound to the authenticated account and must be omitted')
        if set(paths) - (set(expected) - {'userID'}):
            raise ValueError('Unknown path parameter')
        actual = dict(paths)
        if 'userID' in expected:
            actual['userID'] = user_id
        path = op['path']
        for key, p in expected.items():
            if key not in actual:
                raise ValueError(f'Missing path parameter: {key}')
            value = actual[key]
            self._validate(value, p.get('schema', {}), f'path.{key}')
            if isinstance(value, bool) or not re.fullmatch(r'[A-Za-z0-9_-]+', str(value)):
                raise ValueError(f'Unsafe path parameter: {key}')
            path = path.replace('{' + key + '}', str(value))
        props = {p['name']: p.get('schema', {}) for p in op['parameters'] if p['in'] == 'query'}
        required = [p['name'] for p in op['parameters'] if p['in'] == 'query' and p.get('required')]
        if op['method'] == 'GET' and name.startswith('List_all_'):
            props.update(PAGINATION)
        self._validate(query, {'type': 'object', 'properties': props, 'required': required, 'additionalProperties': False}, 'query')
        if 'body' in arguments:
            if op['method'] == 'GET' or op['body_schema'] is None:
                raise ValueError('This operation does not accept a body')
            self._validate(arguments['body'], _request_schemas(op['body_schema']), 'body')
            if op['binary_upload']:
                self._validate_upload(arguments['body'])
        elif op['body_required']:
            raise ValueError('body is required')
        result = {'method': op['method'], 'path': path, 'query': copy.deepcopy(query),
                  'body': copy.deepcopy(arguments.get('body'))}
        if op['binary_upload']:
            result['binary_upload'] = True
        return result

    @staticmethod
    def _validate_upload(body):
        try:
            raw = base64.b64decode(body['data_base64'], validate=True)
        except (binascii.Error, ValueError) as exc:
            raise ValueError('body.data_base64 must contain valid standard base64') from exc
        if not raw or len(raw) > MAX_UPLOAD_BYTES:
            raise ValueError('Attachment must contain 1 byte to 10 MiB')
        signatures = {
            'image/png': (b'\x89PNG\r\n\x1a\n',),
            'image/jpeg': (b'\xff\xd8\xff',),
            'image/gif': (b'GIF87a', b'GIF89a'),
        }
        if not raw.startswith(signatures[body['content_type']]):
            raise ValueError('Attachment file signature does not match content_type')
        if not body['description'].strip():
            raise ValueError('Attachment description must not be blank')

    validate = prepare
