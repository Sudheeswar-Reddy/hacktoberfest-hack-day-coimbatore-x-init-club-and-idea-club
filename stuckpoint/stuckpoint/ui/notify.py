import platform

def notify(title: str, body: str) -> None:
    try:
        if platform.system() == "Darwin":
            import subprocess
            subprocess.run([
                'osascript', '-e',
                f'display notification "{body}" with title "{title}"'
            ], check=False)
        else:
            from plyer import notification
            notification.notify(
                title=title,
                message=body,
                app_name="StuckPoint",
                timeout=10
            )
    except Exception as e:
        print(f"Failed to send notification: {e}")
