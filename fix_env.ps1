# Fix OLLAMA_HOST environment variable
# Remove from all levels and let .env file handle it

[System.Environment]::SetEnvironmentVariable('OLLAMA_HOST', $null, 'User')
[System.Environment]::SetEnvironmentVariable('OLLAMA_HOST', $null, 'Process')

Write-Host "✅ Removed OLLAMA_HOST from environment variables"
Write-Host "⚠️ Please restart your terminal/PowerShell for changes to take effect"
