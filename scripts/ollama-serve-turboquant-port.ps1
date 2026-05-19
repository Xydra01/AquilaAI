# Start TurboQuant Ollama on port 11435 so it does not fight the system tray Ollama on 11434.
# Aquila: set OLLAMA_BASE_URL=http://127.0.0.1:11435 in .env
& "$PSScriptRoot\ollama-serve-turboquant.ps1" -Port 11435 @args
