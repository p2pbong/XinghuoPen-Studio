' XingHuoPen launcher - windowless edition.
' Double-click this file: starts the UI (pythonw). pythonw itself
' is a GUI-subsystem exe and has NO console, so nothing flashes.
' IMPORTANT: window style must be 1 (normal), NOT 0 (hidden).
' Style 0 is meant for hiding a CONSOLE window; for Qt GUI apps
' it also hides the app window itself (v1.84 bug: the app ran but
' no window appeared).
' Keep this file PURE ASCII: Windows Script Host reads .vbs in the
' ANSI codepage, non-ASCII bytes would garble.
Option Explicit
Dim fso, shell, root, exe, script, cmd
Set fso = CreateObject("Scripting.FileSystemObject")
Set shell = CreateObject("WScript.Shell")
root = fso.GetParentFolderName(WScript.ScriptFullName) & "\"
exe = root & "env\pythonw.exe"
script = root & "src\main.py"
If Not fso.FileExists(exe) Then
    MsgBox "Bundled Python environment not found:" & vbCrLf & exe & vbCrLf & vbCrLf & _
           "This XingHuoPen folder is incomplete." & vbCrLf & _
           "Please re-extract the full package.", _
           vbCritical + vbOKOnly, "XingHuoPen - Launch Failed"
    WScript.Quit 1
End If
cmd = """" & exe & """ """ & script & """"
shell.Run cmd, 1, False