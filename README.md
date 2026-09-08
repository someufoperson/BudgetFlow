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

Transfers between accounts, balance reconciliation, reminders, debt repayment planning, and purchase recommendations are not available yet. A credit limit is stored as account information; it does not increase the account balance or count as income.

___

**TODO**

- [ ] 👾 User interface: a web interface for transactions, budget expectations, and debt obligations, along with a richer conversational CLI
- [ ] 🤖 AI: analysis of income and expenses, purchase recommendations, and support for building and maintaining a budget strategy
- [ ] 👤 Personalization: user preferences, savings goals, expected income and expenses, and configurable reminders
- [ ] 💰 Budget: transfers between accounts, balance reconciliation, debt accounting, deposit interest, and support for other financial instruments
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
