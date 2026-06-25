' Lanceur silencieux du watchdog Memento.
'
' VBS est natif Windows et ne montre AUCUNE fenetre quand on lance un .ps1.
' La combinaison Run "...", 0, False = fenetre cachee + ne pas attendre.
'
' Contrainte Collins : aucune fenetre ne doit flasher au demarrage de la borne
' (ni au boot, ni quand le watchdog redemarre l'agent).

Option Explicit

Dim shell, scriptDir, ps1Path, cmd

Set shell = CreateObject("WScript.Shell")
scriptDir = CreateObject("Scripting.FileSystemObject").GetParentFolderName(WScript.ScriptFullName)
ps1Path = scriptDir & "\watchdog.ps1"

cmd = "powershell.exe -NoProfile -NonInteractive -WindowStyle Hidden -ExecutionPolicy Bypass -File """ & ps1Path & """"

shell.Run cmd, 0, False
