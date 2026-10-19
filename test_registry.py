import base64
import unittest
from registry import Registry


class RegistryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.r = Registry()

    def test_full_catalog_and_pagination(self):
        a = self.r.catalog(limit=100)
        self.assertGreater(a['total'], 400)
        self.assertEqual(a['next_cursor'], 100)
        b = self.r.catalog(cursor=100, limit=100)
        self.assertFalse({o['name'] for o in a['operations']} & {o['name'] for o in b['operations']})

    def test_authenticated_user_binding(self):
        result = self.r.prepare('List_all_MonetaryAccount_for_User', {}, 42)
        self.assertEqual(result, {'method': 'GET', 'path': '/user/42/monetary-account', 'query': {}, 'body': None})
        with self.assertRaisesRegex(ValueError, 'bound'):
            self.r.prepare('List_all_MonetaryAccount_for_User', {'path': {'userID': 43}}, 42)

    def test_path_type_and_injection(self):
        for value in ['1/../../session', '1?foo=2', '1%2f2', '..', '1', True]:
            with self.subTest(value=value), self.assertRaises(ValueError):
                self.r.prepare('READ_MonetaryAccountBank_for_User', {'path': {'itemId': value}}, 42)
        result = self.r.prepare('READ_MonetaryAccountBank_for_User', {'path': {'itemId': 1}}, 42)
        self.assertEqual(result['path'], '/user/42/monetary-account-bank/1')

    def test_unknown_arguments(self):
        name = 'List_all_MonetaryAccount_for_User'
        for args in [{'url': 'https://elsewhere'}, {'path': {'other': 1}}, {'query': {'unknown': 1}}, {'body': {}}]:
            with self.subTest(args=args), self.assertRaises(ValueError):
                self.r.prepare(name, args, 42)
        with self.assertRaises(ValueError):
            self.r.prepare('arbitrary-operation', {}, 42)

    def test_pagination(self):
        name = 'List_all_MonetaryAccount_for_User'
        result = self.r.prepare(name, {'query': {'count': 50, 'older_id': 123}}, 42)
        self.assertEqual(result['query']['count'], 50)
        for q in [{'count': '50'}, {'count': 201}, {'older_id': -1}]:
            with self.assertRaises(ValueError):
                self.r.prepare(name, {'query': q}, 42)

    def test_nonfinancial_write_and_schema(self):
        name = 'CREATE_NoteText_for_User_MonetaryAccount_Payment'
        args = {'path': {'monetary-accountID': 3, 'paymentID': 4}, 'body': {'content': 'Receipt reconciled'}}
        self.assertEqual(self.r.prepare(name, args, 42)['method'], 'POST')
        for body in [{'content': 5}, {'content': 'ok', 'surprise': 1}]:
            with self.assertRaises(ValueError):
                self.r.prepare(name, {**args, 'body': body}, 42)

    def test_ref_required_fields_and_unknown_nested(self):
        name = 'CREATE_CustomerStatement_for_User_MonetaryAccount'
        args = {'path': {'monetary-accountID': 3}, 'body': {'statement_format': 'CSV', 'date_start': '2026-01-01', 'date_end': '2026-02-01'}}
        self.assertEqual(self.r.prepare(name, args, 42)['body']['statement_format'], 'CSV')
        with self.assertRaisesRegex(ValueError, 'required'):
            self.r.prepare(name, {**args, 'body': {'statement_format': 'CSV'}}, 42)

    def test_money_and_credentials_unavailable(self):
        for name in ['CREATE_Payment_for_User_MonetaryAccount', 'CREATE_DraftPayment_for_User_MonetaryAccount',
                     'UPDATE_RequestResponse_for_User_MonetaryAccount', 'CREATE_SessionServer',
                     'CREATE_DeviceServer', 'CREATE_Installation']:
            with self.subTest(name=name):
                self.assertFalse(self.r.operations[name]['available'])
                with self.assertRaises(ValueError):
                    self.r.prepare(name, {}, 42)
        self.assertTrue(self.r.operations['List_all_Payment_for_User_MonetaryAccount']['available'])

    def test_binary_uploads(self):
        body = {'data_base64': base64.b64encode(b'\x89PNG\r\n\x1a\nimage').decode(),
                'content_type': 'image/png', 'description': 'Receipt'}
        names = ['CREATE_AttachmentPublic', 'CREATE_Attachment_for_User_MonetaryAccount']
        for name in names:
            op = self.r.learn([name])[0]
            self.assertTrue(op['available'])
            self.assertTrue(op['binary_upload'])
            args = {'body': body}
            if name != 'CREATE_AttachmentPublic':
                args['path'] = {'monetary-accountID': 3}
            result = self.r.prepare(name, args, 42)
            self.assertTrue(result['binary_upload'])
            self.assertEqual(result['body'], body)
        for invalid in [
            {**body, 'data_base64': 'nonsense!'},
            {**body, 'content_type': 'image/jpeg'},
            {**body, 'content_type': 'text/html'},
            {**body, 'description': ' '},
            {**body, 'description': 'Header\r\ninjected'},
            {**body, 'description': 'a' * 141},
            {**body, 'data_base64': base64.b64encode(b'GIF89a' + b'x' * (10 * 1024 * 1024)).decode(), 'content_type': 'image/gif'},
        ]:
            with self.assertRaises(ValueError):
                self.r.prepare('CREATE_AttachmentPublic', {'body': invalid}, 42)

    def test_empty_nonfinancial_body(self):
        for name, path in [
            ('CREATE_ExportRib_for_User_MonetaryAccount', {'monetary-accountID': 3}),
            ('UPDATE_InvoiceExport_for_User_Invoice', {'invoiceID': 3, 'itemId': 4}),
            ('CREATE_InvoiceExport_for_User_Invoice', {'invoiceID': 3}),
            ('CREATE_Statement_for_User_MonetaryAccount_Event', {'monetary-accountID': 3, 'eventID': 4}),
        ]:
            with self.subTest(name=name):
                self.assertTrue(self.r.operations[name]['available'])
                self.assertEqual(self.r.prepare(name, {'path': path, 'body': {}}, 42)['body'], {})
                with self.assertRaises(ValueError):
                    self.r.prepare(name, {'path': path, 'body': {'undocumented': True}}, 42)

    def test_funds_verification_and_card_replacement_classification(self):
        self.assertTrue(self.r.operations['CREATE_ConfirmationOfFunds_for_User']['available'])
        replace = self.r.operations['CREATE_Replace_for_User_Card']
        self.assertFalse(replace['available'])
        self.assertIn('fee-bearing', replace['unavailable_reason'])

    def test_learn_only_relevant_schema(self):
        op = self.r.learn(['CREATE_CustomerStatement_for_User_MonetaryAccount'])[0]
        self.assertIn('ExportStatement', op['schema_definitions'])
        self.assertLess(len(op['schema_definitions']), 20)
        self.assertNotIn('userID', op['arguments']['path'])


if __name__ == '__main__':
    unittest.main()
