import { useAccounts } from '../hooks/useAccounts'

export default function AccountsPanel() {
  const { accounts, loading, addAccount, removeAccount } = useAccounts()

  if (loading) return <div className="text-gray-400">Loading accounts...</div>

  return (
    <div>
      <div className="flex items-center justify-between mb-4">
        <h3 className="text-lg font-bold">Connected Accounts</h3>
        <button
          onClick={addAccount}
          className="px-4 py-1.5 bg-accent hover:bg-blue-700 rounded text-sm text-white transition-colors"
        >
          + Add Google Account
        </button>
      </div>

      {accounts.length === 0 ? (
        <p className="text-sm text-gray-400">
          No accounts connected. Add a Google account to sync your calendar and email.
        </p>
      ) : (
        <div className="space-y-2">
          {accounts.map((account) => (
            <div
              key={account.id}
              className="flex items-center justify-between p-3 bg-gray-800 rounded-lg"
            >
              <div>
                <p className="text-white text-sm font-medium">{account.email}</p>
                <p className="text-xs text-gray-400">
                  {account.last_sync
                    ? `Last synced: ${new Date(account.last_sync).toLocaleString()}`
                    : 'Never synced'}
                </p>
              </div>
              <button
                onClick={() => removeAccount(account.id)}
                className="text-red-400 hover:text-red-300 text-sm transition-colors"
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
