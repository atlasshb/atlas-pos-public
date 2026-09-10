' Hidden launcher for atlas-posd
Set sh = CreateObject("WScript.Shell")
sh.CurrentDirectory = "C:\atlas-pos\posd"
sh.Run "py -3 C:\atlas-pos\posd\agent.py", 0, False
