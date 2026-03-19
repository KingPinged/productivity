import { useAccounts } from '../hooks/useAccounts'

export default function AccountsPanel() {
  const { accounts, loading, addAccount, removeAccount } = useAccounts()

  if (loading) return <div className="text-muted">Loading accounts...</div>

  return (
    <div>
      <div className="flex items-center justify-between mb-4">
        <h3 className="font-display font-bold text-lg text-primary">Connected Accounts</h3>
        <button
          onClick={addAccount}
          className="px-4 py-1.5 bg-accent hover:bg-accent-hover rounded-xl text-sm text-white transition-colors"
        >
          + Add Google Account
        </button>
      </div>

      {accounts.length === 0 ? (
        <p className="text-sm text-secondary">
          No accounts connected. Add a Google account to sync your calendar and email.
        </p>
      ) : (
        <div className="space-y-2">
          {accounts.map((account) => (
            <div
              key={account.id}
              className="flex items-center justify-between p-4 bg-sand rounded-xl"
            >
              <div>
                <p className="text-primary text-sm font-medium">{account.email}</p>
                <p className="text-xs text-secondary">
                  {account.last_sync
                    ? `Last synced: ${new Date(account.last_sync).toLocaleString()}`
                    : 'Never synced'}
                </p>
              </div>
              <button
                onClick={() => removeAccount(account.id)}
                className="text-urgent/60 hover:text-urgent text-sm transition-colors"
              >
                Remove
              </button>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
