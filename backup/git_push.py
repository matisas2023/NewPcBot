import os
import subprocess

# ===== Налаштування =====
GITHUB_URL = "https://github.com/matisas2023/NewPcBot.git"  # заміни на свій репозиторій
COMMIT_MESSAGE = "Initial commit – обновлено весь проект та розширено функціонал"

# ===== Функції =====
def run(cmd):
    """Запуск команди Git у терміналі"""
    result = subprocess.run(cmd, shell=True, text=True, capture_output=True)
    if result.returncode != 0:
        print(f"Помилка: {result.stderr}")
    else:
        print(result.stdout)

# ===== 1. Ініціалізація Git =====
if not os.path.exists(".git"):
    print("Ініціалізація Git...")
    run("git init")

# ===== 2. Додавання всіх файлів =====
print("Додаємо всі файли...")
run("git add .")

# ===== 3. Коміт =====
print(f"Створюємо коміт: {COMMIT_MESSAGE}")
run(f'git commit -m "{COMMIT_MESSAGE}"')

# ===== 4. Підключення Remote =====
print(f"Підключаємо remote: {GITHUB_URL}")
run("git remote remove origin")  # на випадок, якщо origin вже існує
run(f"git remote add origin {GITHUB_URL}")

# ===== 5. Push =====
print("Виконуємо пуш на GitHub...")
run("git branch -M main")  # перейменовуємо гілку у main
run("git push -u origin main")
