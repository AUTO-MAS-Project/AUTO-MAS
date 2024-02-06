import os

os.system("pyinstaller -F -i res/AUTO_MAA.ico manage.py")
os.system("pyinstaller -F -i res/AUTO_MAA.ico run.py")
os.system("pyinstaller -F -i res/AUTO_MAA.ico AUTO_MAA.py")