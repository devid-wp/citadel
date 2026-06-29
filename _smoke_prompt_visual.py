"""Visual smoke: напечатать prompt в разных темах."""
import sys, os
sys.path.insert(0, 'D:\\citadel')

from core.repl import build_prompt
from core.theme_state import get_theme_state, Theme

state = get_theme_state()
themes = [Theme.DAY, Theme.EVENING, Theme.NIGHT]

print("Three themes side by side:")
print("-" * 60)
for theme in themes:
    state.set_theme(theme, force_notify=True)
    p = build_prompt(palette=state.current_palette,
                     cwd=os.getcwd(),
                     user_name="dev",
                     version="3.0")
    print(f"  {theme.value:<8} | {p}")
print("-" * 60)
print("Notice: color changes left-to-right, content identical.")
