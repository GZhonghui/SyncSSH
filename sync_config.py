############################################################
# https://github.com/GZhonghui/SyncSSH, Author: GZhonghui

# 远程服务器配置
ssh_server_host = "192.168.100.90"
ssh_server_port = 22
ssh_server_platform = "windows" # 可选: linux, windows, macos
ssh_server_username = "admin"

# 为了兼容多平台 路径不直接使用字符串 这些字符串是相对于 home 的路径
ssh_server_path = ["Desktop", "sync", "project_name"]

sync_ignore_folders = ["__pycache__", ".git", ".vscode"] # 忽略的文件夹 优先级最高

sync_file_names = ["Makefile", "Dockerfile"] # 一定会同步的文件名

sync_file_extensions = [ # 同步的文件类型
    ".py", # Python
    ".h", ".c", ".cpp", ".hpp", # C/C++
    ".sh", ".bat", ".zsh", # shell
    ".txt", # requirements.txt CMakeLists.txt
    ".json" # config.json
]

############################################################