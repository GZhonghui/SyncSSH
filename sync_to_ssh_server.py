############################################################
# https://github.com/GZhonghui/SyncSSH, Author: GZhonghui

# 安装 watchdog: python -m pip install watchdog
# 安装 sshpass: brew install sshpass
# 修改以下的配置 然后执行: python sync_to_ssh_server.py

# 远程服务器配置
ssh_server_host = "192.168.100.90"
ssh_server_port = 22
ssh_server_platform = "windows" # 可选: linux, windows, macos
ssh_server_username = "admin"
ssh_server_password = "" # 密码在程序执行时手动输入

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

# 从 sync_config.py 中导入配置
# TODO: 可以用更优雅的写法实现
try:
    import sync_config
    ssh_server_host = sync_config.ssh_server_host
    ssh_server_port = sync_config.ssh_server_port
    ssh_server_platform = sync_config.ssh_server_platform
    ssh_server_username = sync_config.ssh_server_username
    ssh_server_path = sync_config.ssh_server_path
    sync_ignore_folders = sync_config.sync_ignore_folders
    sync_file_names = sync_config.sync_file_names
    sync_file_extensions = sync_config.sync_file_extensions
except ImportError:
    ...

import os, sys, time, getpass, subprocess, importlib.util, ntpath, posixpath
from pathlib import Path

# 支持的平台
supported_platforms = ["windows", "linux", "macos"]

# 路径构建器
path_builders = {
    "windows": ntpath,
    "linux": posixpath,
    "macos": posixpath
}

# 远程服务器根路径
base_paths = {
    "windows": [f"C:{ntpath.sep}", "Users", ssh_server_username, *ssh_server_path],
    "linux": ["/", "home", ssh_server_username, *ssh_server_path],
    "macos": ["/", "Users", ssh_server_username, *ssh_server_path]
}

# 创建远程目录的命令
def mkdir_command(remote_dir: str) -> str:
    return {
        "windows": f'if not exist "{remote_dir}" mkdir "{remote_dir}"',
        "linux": f"mkdir -p '{remote_dir}'",
        "macos": f"mkdir -p '{remote_dir}'"
    }[ssh_server_platform]

# 日志输出
def log(*args, **kwargs):
    timestamp = time.strftime("[%H:%M:%S]", time.localtime())
    print(timestamp, *args, **kwargs, file=sys.stdout)

# 检查配置
def check_config() -> bool:
    # 检查密码
    # 如果不在一开始就检查密码的话 可能会因为密码错误太多次 导致账户被锁定
    # TODO

    # 检查平台
    if ssh_server_platform not in supported_platforms:
        log(f"unsupported platform: {ssh_server_platform}")
        return False

    # 检查 watchdog
    if not importlib.util.find_spec("watchdog"):
        log("watchdog not found, exiting...")
        return False

    return True

# 获取本地根路径
def get_local_root_path() -> str:
    return os.path.dirname(os.path.abspath(__file__))

# 获取远程根路径
def get_remote_root_path() -> str:
    return path_builders[ssh_server_platform].join(*base_paths[ssh_server_platform])

# 只处理文件路径 并且参数和返回值都是绝对路径
def convert_local_file_path_to_remote(file_path: str) -> dict | None:
    """
    将本地文件路径转换为: 远程文件路径 & 远程文件所在目录
    
    Args:
        file_path: 本地文件的绝对路径
    Returns:
        dict: 远程文件路径 & 远程文件所在目录
    """
    # 获取本地和远程根路径
    local_root = get_local_root_path()
    remote_root = get_remote_root_path()
    
    # 检查文件是否在本地根路径下
    if not os.path.commonprefix([local_root, file_path]) == local_root:
        return None
    
    # 获取相对路径
    rel_path = os.path.relpath(file_path, local_root)
    
    rel_path = rel_path.replace(os.sep, path_builders[ssh_server_platform].sep)
    remote_file_path = path_builders[ssh_server_platform].join(remote_root, rel_path)
    
    return {
        "remote_file_path": remote_file_path,
        "remote_file_dir": path_builders[ssh_server_platform].dirname(remote_file_path)
    }

# 创建远程目录
def make_remote_dir(remote_dir: str) -> bool:
    """
    在远程服务器上创建目录
    
    Args:
        remote_dir: 远程服务器上的目录路径
    Returns:
        bool: 是否创建成功
    """
    # 根据平台选择创建目录的命令
    mkdir_command_value = mkdir_command(remote_dir)
    
    # 构建 ssh 命令
    ssh_command = [
        "sshpass",
        "-p", ssh_server_password,
        "ssh",
        "-p", str(ssh_server_port), # ssh 使用小写 p 指定端口（-P 是 scp 的选项）
        f"{ssh_server_username}@{ssh_server_host}",
        mkdir_command_value
    ]
    
    try:
        # 执行 ssh 命令
        result = subprocess.run(
            ssh_command,
            check=True, 
            capture_output=True,
            text=True
        )
        # log(f"directory created: {remote_dir}")
        return True
        
    except subprocess.CalledProcessError as e:
        log(f"create directory failed: {e.stderr}")
        return False

# 注意: 这个函数是同步单个文件 不是同步目录
def upload_file_to_remote(local_path: str, remote_path: str | None, remote_dir: str | None) -> bool:
    """
    通过 scp 将本地文件同步到远程服务器
    Args:
        local_path: 本地文件路径
        remote_path: 远程服务器上的目标路径
        remote_dir: 远程文件所在目录
    """

    # 检查本地文件路径
    if local_path == "":
        log(f"local path is empty")
        return False

    # 检查远程文件路径和目录
    if not remote_path or not remote_dir:
        remote_info = convert_local_file_path_to_remote(local_path)
        if not remote_info:
            log(f"convert local file path to remote failed: {local_path}")
            return False
        remote_path = remote_info["remote_file_path"]
        remote_dir = remote_info["remote_file_dir"]

    # 检查本地文件是否存在
    if not os.path.exists(local_path):
        log(f"local file not found: {local_path}")
        return False
    file_size = os.path.getsize(local_path)
    
    # 创建远程目录
    if not make_remote_dir(remote_dir):
        log(f"create remote directory failed: {remote_dir}")
        return False
    
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
        log(f"file upload success: {local_path}({file_size / 1024} KB) -> {remote_path}")
        return True
        
    except subprocess.CalledProcessError as e:
        log(f"file upload failed: {e.stderr}")
        return False

# 文件修改
def on_file_modified(file_path: str):
    log(f"file modified: {file_path}")
    upload_file_to_remote(file_path, None, None)

# 文件创建
def on_file_created(file_path: str):
    log(f"file created: {file_path}")
    upload_file_to_remote(file_path, None, None)

# 文件删除
def on_file_deleted(file_path: str):
    log(f"file deleted: {file_path}")
    # TODO: 删除远程文件

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
    # 遍历本地根目录下的所有文件
    local_root = get_local_root_path()
    for root, dirs, files in os.walk(local_root):
        # 过滤掉需要忽略的文件夹
        dirs[:] = [d for d in dirs if d not in sync_ignore_folders]
        
        # 处理每个文件
        for file in files:
            file_path = os.path.join(root, file)
            if should_process_file(file_path):
                log(f"init: upload file {file_path}")
                on_file_created(file_path)
    log("init: upload all files success")

def main():
    log("start sync to ssh server")

    log(f"sync from: {get_local_root_path()}")
    log(f"sync to: {get_remote_root_path()}")

    # 同步文件
    start_upload_all_files()
    # BUG: 在初始化完成之前 不会监听文件变化
    start_watch_files()

if __name__ == "__main__":
    # 检查配置
    if check_config():
        ssh_server_password = getpass.getpass("input password: ")
        main()
    else:
        log("check config failed, exiting...")
        exit(0)
