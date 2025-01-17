############################################################
# 安装 watchdog: python -m pip install watchdog
# 安装 sshpass: brew install sshpass
# 修改以下的配置 然后执行: python sync_to_ssh_server.py

# 远程服务器配置
ssh_server_host = "192.168.100.90"
ssh_server_port = 22
ssh_server_platform = "windows" # 可选: linux, windows, macos
ssh_server_username = "admin"
ssh_server_password = "" # 密码在程序执行时手动输入

# 为了兼容多平台 路径不直接使用字符串
# 这些字符串是相对于桌面的路径 比如以下配置对应的路径在 linux 下是: ~/sync/project_name
ssh_server_path = ["sync", "project_name"]

sync_ignore_folders = [".git", "__pycache__", ".vscode"] # 忽略的文件夹 优先级最高

sync_file_names = ["Makefile", "Dockerfile"] # 一定会同步的文件名

sync_file_extensions = [ # 同步的文件类型
    ".py", # Python
    ".h", ".c", ".cpp", ".hpp", # C/C++
    ".sh", ".bat", ".zsh", # shell
    ".txt", # requirements.txt CMakeLists.txt
    ".json" # config.json
]

############################################################

import os, sys, time, getpass, subprocess, importlib.util, ntpath, posixpath
from pathlib import Path

# 日志输出
def log(*args, **kwargs):
    timestamp = time.strftime("[%H:%M:%S]", time.localtime())
    print(timestamp, *args, **kwargs, file=sys.stdout)

# 注意: 这个函数是同步单个文件 不是同步目录
def upload_file_to_remote(local_path: str, remote_path: str):
    """
    通过 scp 将本地文件同步到远程服务器
    Args:
        local_path: 本地文件路径
        remote_path: 远程服务器上的目标路径
    """

    # 检查参数
    if local_path == "" or remote_path == "":
        log(f"local path or remote path is empty")
        return False

    # 检查本地文件是否存在
    if not os.path.exists(local_path):
        log(f"local file not found: {local_path}")
        return False
    
    # TODO: 检查远程路径是否存在
        
    # 构建 scp 命令        
    scp_command = [
        "sshpass",
        "-p", ssh_server_password,
        "scp",
        "-P", str(ssh_server_port),
        local_path,
        f"{ssh_server_username}@{ssh_server_host}:{remote_path}"
    ]
    
    try:
        # 执行 scp 命令
        result = subprocess.run(
            scp_command, 
            check=True,
            capture_output=True,
            text=True
        )
        log(f"file upload success: {local_path} -> {remote_path}")
        return True
        
    except subprocess.CalledProcessError as e:
        log(f"file upload failed: {e.stderr}")
        return False

# 获取本地根路径
def get_local_root_path() -> str:
    return os.path.dirname(os.path.abspath(__file__))

# 获取远程根路径
def get_remote_root_path() -> str:
    if ssh_server_platform == "windows":
        remote_path = ntpath.join(f"C:{ntpath.sep}", "Users", ssh_server_username, *ssh_server_path)
    elif ssh_server_platform == "linux":
        remote_path = posixpath.join("/", "home", ssh_server_username, *ssh_server_path)
    elif ssh_server_platform == "macos":
        remote_path = posixpath.join("/", "Users", ssh_server_username, *ssh_server_path)
    else:
        log(f"unsupported platform: {ssh_server_platform}")
        exit(0)
    return remote_path

# 将本地文件路径转换为远程文件路径 一定是文件 并且参数和返回值都是绝对路径
def convert_local_file_path_to_remote(file_path: str) -> str:
    """将本地文件路径转换为远程文件路径
    
    Args:
        file_path: 本地文件的绝对路径
    Returns:
        str: 远程服务器上对应的绝对路径，转换失败返回空字符串
    """
    # 获取本地和远程根路径
    local_root = get_local_root_path()
    remote_root = get_remote_root_path()
    
    # 检查文件是否在本地根路径下
    if not os.path.commonprefix([local_root, file_path]) == local_root:
        return ""
    
    # 获取相对路径
    rel_path = os.path.relpath(file_path, local_root)
    
    # 根据目标平台转换路径分隔符
    if ssh_server_platform == "windows":
        rel_path = rel_path.replace(os.sep, ntpath.sep)
        return ntpath.join(remote_root, rel_path)
    else: # linux, macos
        rel_path = rel_path.replace(os.sep, posixpath.sep)
        return posixpath.join(remote_root, rel_path)

# 文件修改
def on_file_modified(file_path: str):
    remote_file_path = convert_local_file_path_to_remote(file_path)
    if remote_file_path != "":
        log(f"file modified: {file_path}, remote: {remote_file_path}")
        upload_file_to_remote(file_path, remote_file_path)
    else:
        log(f"file modified: {file_path}, remote: not found")

# 文件删除
def on_file_deleted(file_path: str):
    remote_file_path = convert_local_file_path_to_remote(file_path)
    if remote_file_path != "":
        log(f"file deleted: {file_path}, remote: {remote_file_path}")
        upload_file_to_remote(file_path, remote_file_path)
    else:
        log(f"file deleted: {file_path}, remote: not found")

# 文件创建
def on_file_created(file_path: str):
    remote_file_path = convert_local_file_path_to_remote(file_path)
    if remote_file_path != "":
        log(f"file created: {file_path}, remote: {remote_file_path}")
        upload_file_to_remote(file_path, remote_file_path)
    else:
        log(f"file created: {file_path}, remote: not found")

# 检查文件是否需要处理 使用绝对路径
def should_process_file(file_path: str) -> bool:
    path = Path(file_path)

    # 检查是否在忽略文件夹中
    for ignore_folder in sync_ignore_folders:
        if ignore_folder in path.parts:
            return False
    
    # 检查是否是指定文件名
    if path.name in sync_file_names:
        return True
    
    # 检查文件扩展名
    return path.suffix in sync_file_extensions

# 开始监控文件
def start_watch_files():
    from watchdog.observers import Observer
    from watchdog.events import FileSystemEventHandler
    
    class FileHandler(FileSystemEventHandler):                
        # 以下事件处理函数 只处理文件 不处理目录
        def on_created(self, event):
            if not event.is_directory and should_process_file(event.src_path):
                on_file_created(event.src_path)
        
        def on_modified(self, event):
            if not event.is_directory and should_process_file(event.src_path):
                on_file_modified(event.src_path)
        
        def on_deleted(self, event):
            if not event.is_directory and should_process_file(event.src_path):
                on_file_deleted(event.src_path)

        def on_moved(self, event):
            if not event.is_directory:
                if should_process_file(event.src_path):
                    on_file_deleted(event.src_path)
                if should_process_file(event.dest_path):
                    on_file_created(event.dest_path)
    
    # 创建观察者和事件处理器
    observer = Observer()
    handler = FileHandler()
    
    # 开始递归监控当前目录及其所有子目录
    observer.schedule(handler, get_local_root_path(), recursive=True)
    observer.start()
    
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        observer.stop()
        
    log("stop sync to ssh server, bye")
    observer.join()

# 开始上传所有文件 初始化时执行
def start_upload_all_files():
    ...

def main():
    log("start sync to ssh server")

    log(f"sync from: {get_local_root_path()}")
    log(f"sync to: {get_remote_root_path()}")

    # 同步文件
    start_watch_files()

if __name__ == "__main__":
    if not importlib.util.find_spec("watchdog"):
        log("watchdog not found, exiting...")
        exit(0)
    get_remote_root_path() # 检查能不能计算出远程路径 如果不能则退出
    ssh_server_password = getpass.getpass("input password: ")
    main()
