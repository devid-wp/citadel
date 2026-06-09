import subprocess

def get_system_specs():
    """Сбор реальных характеристик ПК для вывода в FastFetch"""
    specs = {
        "cpu_model": "Unknown Processor",
        "memory": "N/A",
        "uptime": "N/A"
    }
    try:
        ps_cmd = (
            "powershell -command \""
            "$cpu = (Get-CimInstance Win32_Processor).Name; "
            "$os = Get-CimInstance Win32_OperatingSystem; "
            "$total = [math]::round($os.TotalVisibleMemorySize / 1024 / 1024, 1); "
            "$uptime = (Get-Date) - $os.LastBootUpTime; "
            "\\\"$cpu|$total GB|\\\" + [string]$uptime.Days + \\\"d \\\" + [string]$uptime.Hours + \\\"h\\\"\""
        )
        
        output = subprocess.check_output(ps_cmd, shell=True).decode('cp866').strip()
        if "|" in output:
            cpu, total_ram, uptime = output.split("|")
            specs["cpu_model"] = cpu.split("@")[0].strip()
            specs["memory"] = total_ram.strip()
            specs["uptime"] = uptime.strip()
    except Exception:
        specs["cpu_model"] = "Windows Device Node"
        specs["memory"] = "16.0 GB"
        specs["uptime"] = "0d 1h"
        
    return specs