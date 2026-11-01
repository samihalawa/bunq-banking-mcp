# Evidence pitfalls

These rules generalize reconciliation failures; examples contain no private records.

| Evidence | Safe interpretation | Required follow-up |
| --- | --- | --- |
| Many card retries for the same amount | Attempts may be declined, pending or reversed | Inspect payment_status, authorisation_status, settlement_status and clearing_status; count settled payment records once |
| Two settled device orders at the same merchant/price | Could be two real purchases | Match order IDs and shipment/delivery evidence; do not deduplicate on amount alone |
| Cancellation inside a multi-item order | May cancel only a service or accessory | Read the exact cancelled line; verify the device separately |
| Bank fee invoice grouped under a subscription label | Group title does not identify the fee | Read invoice category, item description, quantity and settled status; separate membership from per-use withdrawal fees |
| Invoice date differs from debit date | Different months can both be correct | State calendar basis; keep invoice and cash totals separate |
| A credit note, refund promise or pending dispute | Not settled cash received | Match the completed bank credit; retain disputed/open amount separately |
| Partial refund | Does not establish cancellation | Verify current renewal/plan state |
| New plan after cancellation | May replace the old plan | Reconstruct migration chronology and current account identity |
| Consolidated arrears invoice | May replace earlier unpaid invoices | Reconcile referenced invoice IDs; avoid adding old and consolidated balances |
| A paid annual bundle with hardware/discount | Initial total may differ from renewal | Separate line items and verify next renewal price/date |
| App-store descriptor | Can contain multiple products, hardware or services | Read itemized receipts; separate app renewal from directly billed product and API usage |
| Developer platform subscription and metered use | Both can be legitimate | Inspect seats, CI minutes, storage, bandwidth and API/compute usage separately |
| Credit top-up | Prepayment is cash outflow, not proof of fixed recurring cost | Verify auto-top-up, remaining balance and usage separately |
| Hosting invoice | May combine servers, storage, addresses and tax | Estimate removal of a specific unused resource, including applicable tax, without assuming all hosting can stop |
| Own-account or intermediary funding | May be a transfer or debt repayment | Pair native references and account ownership; leave uncertain legs unresolved |
| Empty transfer descriptions | Do not by themselves make a transfer unmatchable | Require reciprocal known account identities, exact same-currency opposite amounts, subsecond/short chronology and unique matches in both directions; report record matching separately from a provider-native link |
| Explicit owned-account currency conversion | Different currencies cannot have equal nominal amounts | Require the exact shared native conversion marker, matching source amount/currencies, reciprocal identities and unique close timestamps; retain both currency legs and separate fees without inventing an exchange rate |
| Merchant resembles a hardware manufacturer | Can instead be an investment movement | Inspect native transaction type and purchase/dividend descriptions before treating it as retail spending; do not infer investment profit or loss from net bank cash |
| Provider sends failed and successful receipts together | Receipt count is not payment count | Inspect each attachment's actual status, amount and transaction ID; failed attempts do not add cash outflow |
| Marketing or listing invoice | Can be a one-off boost or prepaid acquisition spend | Match product duration and attributable paying customers; a failed renewal is not a current paid subscription |
| Utility tariff change screen | Selection is not an executed contract | Read persisted contract/order confirmation, effective date, price and fees; compare subsequent bill on equal days/consumption |

Electricity: distinguish energy price (per kWh), contracted power (per kW/day), add-on services and taxes. A flat energy price can still have two power periods; three energy periods are a different choice. Estimate a power reduction from the actual billed daily rates, days and taxes, less the verified change fee. Check measured maximum demand and simultaneous appliances before recommending a lower limit. Central heating/cooling does not by itself establish which electrical equipment or charges belong to the flat. Never claim a tariff or power change succeeded from an unsubmitted selection or a login/dashboard screen.

Personal and business: use unknown where purpose is unsupported. Refund eligibility, return windows, tax deductions and contractual rights depend on current terms, delivery dates, invoice ownership and actual use. Cite the applicable evidence; do not turn a possible refund, credit or tax benefit into a confirmed saving.
