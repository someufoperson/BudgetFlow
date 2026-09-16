# BudgetFlow

The BudgetFlow project aims to help users manage and plan their budgets using AI tools.

Keeping track of everyday expenses, controlling impulse purchases, and planning a budget for months or years ahead can be difficult. BudgetFlow aims to make these habits easier by letting users record and review their finances through conversation.

The project plans to introduce features that help users get out of debt, build savings, analyze income and expenses, and develop a budgeting strategy that fits their circumstances.

In the future, a user should be able to ask AI, "Can I afford a new iPhone that costs $1,200?" and receive an answer based on their available funds, upcoming expenses, debts, and savings goals.

*"Beware of small expenses; a small leak will sink a large ship"* — Benjamin Franklin.

___

**BudgetFlow currently has the following features:**

1. Minimalistic CLI interface
2. Recording income and expenses through AI, including multiple transactions in one message
3. Searching transactions by account, category, currency, name, date, and amount, with results displayed in pages
4. Editing transactions and deleting them after confirmation
5. Creating currencies and creating or editing income and expense categories
6. Creating, renaming, deactivating, and restoring accounts, with a default account for new transactions
7. Calculating account balances from an opening balance and subsequent transactions, with support for correcting the opening amount
8. Credit accounts with a separately stored, editable credit limit
9. Assigning previously recorded transactions without an account to an existing account after confirmation
10. Period reports as text or PNG infographics, with totals calculated by Python
11. Recording same-currency transfers between your accounts, viewing and editing them, and deleting mistaken records after confirmation
12. Reconciling current account balances and applying separate balance adjustments after confirmation, with optional explanations
13. Cancelling mistaken adjustments through linked reversing entries, and warnings when restored transaction history overlaps an active adjustment

Reminders, debt repayment planning, and purchase recommendations are not available yet. A credit limit is stored as account information; it does not increase the account balance or count as income.

___

**TODO**

- [ ] 👾 User interface: a web interface for transactions, budget expectations, and debt obligations, along with a richer conversational CLI
- [ ] 🤖 AI: analysis of income and expenses, purchase recommendations, and support for building and maintaining a budget strategy
- [ ] 👤 Personalization: user preferences, savings goals, expected income and expenses, and configurable reminders
- [ ] 💰 Budget: debt repayment planning, deposit interest, and support for other financial instruments
- [ ] 🔐 Security: stronger protection of locally stored data and masking of sensitive information when using external AI providers

___

**Quick Start**

You need Python 3.13 or newer. Create a `.env` file using the `.env.example` template and fill in your settings.

With uv:

```sh
uv sync
uv run python main.py
```

Without uv (Windows PowerShell):

```powershell
python -m venv venv
.\venv\Scripts\Activate.ps1
python -m pip install -e .
python main.py
```

Database migrations run automatically when the application starts. Type `exit` or `quit` to close the console.

**First steps**

Create the currency you want to use if it has not been added yet, then create an account with its current balance. For example:

- "Add the currency US Dollar with code USD and type FIAT."
- "Create an account named Main in USD with a current balance of 500 dollars."
- "Create an expense category named Groceries."
- "I spent 25 dollars on groceries."
- "Show expenses from Main this month."
- "Show my accounts."

The first account becomes the default. New transactions use it unless you explicitly name another account. Each account has one currency, which must match the transaction currency.

The opening balance is tied to a specific moment. Only transactions after that moment affect the calculated balance; earlier transactions remain in the history. You can correct the opening amount, but its date and the account currency cannot be edited. Deactivating an account preserves its history and clears its default status if it was selected.

To create a credit account, specify both its balance and its limit: "Create a credit account named Credit Card in USD with a balance of minus 200 dollars and a credit limit of 1,000 dollars."

**If you already have transactions**

After creating an account, you can ask: "Assign all transactions without an account to Main." The application asks for confirmation and assigns only transactions in that account's currency. Transactions already linked to another account remain unchanged.

If you entered today's balance when creating the account, the older history will not be counted again. This lets you keep existing records and start calculating the account balance from the chosen moment.

**Transfers between your accounts**

- `Record a transfer of 10,000 RUB from Payroll to Savings` records a completed transfer; BudgetFlow does not send money to a bank.
- `Show transfers for September` or `Show transfer #12` displays records.
- `Change the amount of transfer #12 to 9,000 RUB` edits a selected transfer. If it has not been shown yet, review it and repeat the requested change.
- `Delete transfer #12; I recorded it by mistake` or `Delete yesterday's transfer of 10,000 RUB from Payroll to Savings` prepares deletion. Ambiguous descriptions require choosing a record.
- Review both accounts' current balances and the proposed changes, then say `Yes, delete the transfer` or `Cancel`.

Transfers require different active accounts in the same currency and a positive amount. Future dates and currency conversion are unsupported. Negative resulting balances remain allowed; credit limits are not added or used to fund a transfer. Each side respects its account's opening-balance timestamp independently.

Deleting a record does not cancel a bank transfer. It removes only that record's contribution, preserving subsequent transactions. Deletion also works with inactive accounts. If the transfer or the displayed balance effects change while confirmation is pending, BudgetFlow presents a new proposal and requires new consent. Repeated confirmation cannot delete twice.

A bank fee is a separate expense: it is neither created nor deleted automatically with a transfer. Delete a mistaken fee separately through the ordinary expense-deletion confirmation.

**Current balance reconciliation and adjustments**

- `My bank shows 39,500 RUB in Payroll. Reconcile the balance` displays the calculated balance, the supplied actual balance, the difference, and the reconciliation time. This does not write financial data.
- `Accept the actual balance. Explanation: I could not restore the old history` prepares an adjustment. The explanation is optional; without one, BudgetFlow uses neutral text stating that the discrepancy's cause is unknown.
- Review the amount, impact and explanation, then say `Yes, apply the adjustment` or `Cancel`.
- `Change the pending adjustment's explanation to: some old history is missing` prepares a revised proposal; it does not confirm it. Explanations must contain 1–512 characters after trimming.
- `Show adjustments` or `Show adjustment #3` displays history.
- `Reverse adjustment #3. Explanation: it was recorded by mistake` prepares a linked reversing entry. Review the original adjustment and the current balance before/after cancellation, then say `Yes, reverse the adjustment` or `Cancel`.

Reconciliation is available only for the current moment. Matching balances require no adjustment. A changed balance invalidates the old proposal; a new confirmation is required. Adjustments do not edit the opening balance and are not income or expenses. They appear separately in reports.

Cancellation adds the opposite amount to the current balance, preserves later transactions and keeps the original record, reason and link. It also works for inactive accounts. A record can be cancelled only once; cancelling a reversing entry or editing saved adjustment fields is unsupported. To correct an amount, cancel the mistaken adjustment and perform a new reconciliation. An old actual balance is a historical observation, not a statement of the current bank balance.

**Restoring history after an adjustment**

Creating, editing or deleting income, expenses or transfers can change history already covered by an active adjustment. BudgetFlow warns when the changed contribution falls after the account's opening balance and at or before the adjustment's application time. Transfers are checked for each account separately; cancelled adjustments do not trigger this warning.

For example, an adjustment of −500 RUB followed by a restored purchase of 500 RUB can count both amounts. The purchase is still recorded. BudgetFlow keeps the adjustment and offers to view it, cancel it with confirmation, or reconcile again. Matching amounts do not prove that the discrepancy's cause has been found. No adjustment is cancelled automatically. The same warnings apply when saving transactions from screenshots.

**Reports as text or images**

- `Create a report for the last 30 days` returns a text report.
- `Create a report for the last 30 days as an image` returns a PNG infographic.
- `Create a report for August 1–31, 2026 as an image` selects an explicit period.

The AI selects the dates and output format; Python calculates all totals. The default is text and 30 calendar days, including today, in the configured timezone. Supported periods contain 1–366 days and cannot end in the future. Reports cover all transactions; filtering a report to one account or category is not yet supported.

Each currency has its own section or image. Reports include income, expenses, their difference, expense categories, and up to six date intervals of expense totals. Account balances are **current**, not historical period-end balances, and include inactive accounts. Credit limits and debt cards are not added. Transactions without an account contribute to period totals but not account balances.

Transfers are excluded from income and expenses. Adjustments and their reversing entries appear in a separate section, by the date of each entry. Cancelling an adjustment in a later month does not remove it from an earlier month's totals. Cancellation links show the current status; full links accompany PNG reports as text.

Images show the five largest expense categories plus an aggregate of the rest, and three accounts plus an aggregate of the rest. Text reports list all categories and accounts. Up to 12 currencies can be rendered per request; larger reports fall back to text. PNG generation runs in a worker thread using Pillow and the bundled Manrope font, without a browser or image-generation API. If rendering fails, the calculated text report is returned.

The console saves images under `output/reports/` and prints their paths. The MAX handler sends images directly from memory and does not save report files on the server. Console files remain until you remove them.

For a server update, copy the changed source files, Alembic migrations, and the complete `services/fonts/` directory, including `OFL.txt`, run `uv sync`, and restart the application using its existing command. Startup applies the database migrations, including the migration for linked balance adjustment reversals. No new environment variable is required. Update the local `theory_main.py` separately if you deploy the MAX handler: this file, like `uv.lock`, is currently ignored by Git. The rendering font is resolved relative to the source file, so no system font installation is needed on Linux.

**Transactions from screenshots in Max**

The terminal supports the same preview, corrections and confirmation through `/screenshot "C:\Users\User\Pictures\receipt.png"`. Supply one local image per command; paths with spaces work with or without quotes. Relative paths are resolved from the terminal's current directory. After reviewing the preview, enter corrections or use the exact save or cancel command shown by the assistant. Screenshot save, resume and cancel commands are currently recognized only in Russian; follow the application's prompts for these actions. File contents are sent to the configured image model only after local format and size checks.

Attach a screenshot of a receipt or transaction history, optionally with a caption such as "Add expenses from Main". Images sent as files are also supported. The assistant shows up to 20 candidate operations before saving. PDF, DOCX, TXT and CSV import and bank loan cards are no longer supported. Loan contracts and future payment schedules are not imported as transactions.

Dates without a year use the current year in the configured timezone; explicit years are preserved. Today/yesterday are resolved against the current local date. Dates without a time use midnight. The AI selects a category from the existing catalog based on the merchant and transaction purpose. When no account is recognized, the application selects the default account; a currency mismatch still requires clarification. Only unresolved fields and material recognition problems need clarification. For example: "For row 1, use account Main and category Groceries". Use "Exclude row 2" to remove a candidate; row numbers are updated after removal. Transfers between your own accounts and uncompleted operations cannot be saved as ordinary income or expenses.

After reviewing the complete list, send the save command shown in the preview. The resume command shows the current draft; the cancel command discards unsaved rows. Upload another image after completing or cancelling the current import. Repeated confirmations do not recreate saved rows. Identical images already saved in the current session are skipped; this image history is not persisted across restarts. Overlapping screenshots can still contain duplicate operations, so review the list.

Operations are saved individually through the existing transaction services. If one fails, the assistant reports the saved rows and retains only the remaining rows for correction and a new confirmation. Screenshot extraction uses `DOCUMENT_MODEL` (default `deepseek-flash`) with the existing `ENDPOINT` and `API_KEY`. Regular chat uses `MODEL`. Up to 10 JPEG/PNG/GIF/WebP attachments with a combined size of 20 MiB are supported. Original images are processed in memory. The previous bank-credit migration and table models are retained for compatibility with existing databases; stored records are not deleted, but bank-credit cards are no longer available in the assistant.
