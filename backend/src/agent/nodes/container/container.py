import docker
import uuid
import tempfile
import os
import shutil
import tarfile
import io


class PersistentDockerRunner:
    def __init__(self, data_dir="src/agent/nodes/container/data"):
        self.client = docker.from_env()
        self.low_level_client = docker.APIClient(base_url="unix://var/run/docker.sock")

        self.image_tag = f"agent_runner_{uuid.uuid4().hex}"
        self.container_name = f"agent_container_{uuid.uuid4().hex}"
        self.workdir = tempfile.mkdtemp()
        self.container = None
        self.data_dir = data_dir  # new

    def _build_image(self):
        # Copy all files from data directory to workdir (preserving directory structure)
        if os.path.exists(self.data_dir):
            for root, dirs, files in os.walk(self.data_dir):
                # Skip __pycache__ directories
                dirs[:] = [d for d in dirs if d != '__pycache__']
                
                for file in files:
                    # Skip .pyc files
                    if file.endswith('.pyc'):
                        continue
                        
                    src_path = os.path.join(root, file)
                    # Preserve the relative path structure from data/ directory
                    relative_path = os.path.relpath(src_path, self.data_dir)
                    dest_path = os.path.join(self.workdir, relative_path)

                    # Create destination directory if it doesn't exist
                    os.makedirs(os.path.dirname(dest_path), exist_ok=True)

                    # Copy file with metadata preservation
                    shutil.copy2(src_path, dest_path)
                    print(f"Copied: {src_path} -> {dest_path}")

        # Write Dockerfile
        dockerfile = """
        FROM python:3.11-slim
        WORKDIR /app
        # Copy all files directly into /app (files are already at workdir root)
        COPY . /app/
        ENV PIP_ROOT_USER_ACTION=ignore
        RUN pip install --no-cache-dir backtrader pandas
        CMD ["tail", "-f", "/dev/null"]
        """
        dockerfile_path = os.path.join(self.workdir, "Dockerfile")
        with open(dockerfile_path, "w") as f:
            f.write(dockerfile)

        # Build image and stream logs
        build_logs = self.low_level_client.build(
            path=self.workdir, tag=self.image_tag, decode=True
        )

        for chunk in build_logs:
            if "stream" in chunk:
                print(chunk["stream"].strip())

    def _start_container(self):
        self.container = self.client.containers.run(
            image=self.image_tag,
            name=self.container_name,
            volumes={self.workdir: {"bind": "/app", "mode": "rw"}},
            working_dir="/app",
            detach=True,
        )

    def start(self):
        self._build_image()
        self._start_container()

    def upload_file(self, content: str, filename: str):
        """Upload a file to the container, preserving path structure (e.g., subfolders)."""
        tar_stream = io.BytesIO()
        with tarfile.open(fileobj=tar_stream, mode="w") as tar:
            file_data = content.encode()
            tarinfo = tarfile.TarInfo(name=filename)
            tarinfo.size = len(file_data)
            tar.addfile(tarinfo, io.BytesIO(file_data))
        tar_stream.seek(0)

        # Now send it to the container
        result = self.client.api.put_archive(
            self.container.id, path="/app", data=tar_stream.read()
        )
        return result

    def download_file(self, filename: str) -> str:
        """Download a file from the container."""
        exec_log = self.container.exec_run(f"cat /app/{filename}", demux=True)
        stdout, stderr = exec_log.output
        if stderr:
            raise Exception(f"Error downloading file: {stderr.decode()}")
        return (stdout or b"").decode()

    def run_command(self, command: str) -> str:
        """Run a command inside the container."""
        exec_log = self.container.exec_run(command, demux=True)
        stdout, stderr = exec_log.output
        if stderr:
            raise Exception(f"Error running command: {stderr.decode()}")
        return (stdout or b"").decode()

    def run_code(self, code: str, filename="agent_code.py") -> str:
        filepath = os.path.join(self.workdir, filename)
        with open(filepath, "w") as f:
            f.write(code)

        exec_log = self.container.exec_run(f"python /app/{filename}", demux=True)
        stdout, stderr = exec_log.output
        return (stdout or b"").decode() + (stderr or b"").decode()

    def stop(self):
        # download all files from the container to workdir
        download_dir="downloaded_strategies"
        if self.container:
            try:
                # Create local download directory
                os.makedirs(download_dir, exist_ok=True)
                
                # Download all files from app/strategies/ folder
                try:
                    archive, _ = self.container.get_archive('/app/strategies/')
                    
                    # Save the tar archive to a temporary file
                    import tarfile
                    import io
                    
                    # Convert archive generator to bytes
                    archive_data = b''.join(archive)
                    
                    # Extract the tar archive
                    with tarfile.open(fileobj=io.BytesIO(archive_data)) as tar:
                        # Extract all files to download directory
                        tar.extractall(path=download_dir)
                        print(f"Downloaded strategies folder to: {download_dir}")
                        
                        # List downloaded files
                        for member in tar.getmembers():
                            if member.isfile() and "__pycache__" not in member.name:
                                print(f"Downloaded: {member.name}")
                                
                except Exception as e:
                    print(f"Error downloading strategies folder: {e}")
                    # Try to download individual files if folder download fails
                    try:
                        # List files in strategies directory first
                        exec_result = self.container.exec_run('find /app/strategies -type f')
                        if exec_result.exit_code == 0:
                            files = exec_result.output.decode().strip().split('\n')
                            for file_path in files:
                                if file_path:  # Skip empty lines
                                    try:
                                        archive, _ = self.container.get_archive(file_path)
                                        archive_data = b''.join(archive)
                                        
                                        with tarfile.open(fileobj=io.BytesIO(archive_data)) as tar:
                                            tar.extractall(path=download_dir)
                                            print(f"Downloaded: {file_path}")
                                    except Exception as file_error:
                                        print(f"Failed to download {file_path}: {file_error}")
                    except Exception as list_error:
                        print(f"Failed to list files in strategies folder: {list_error}")
                
                # Stop and remove container
                self.container.stop()
                self.container.remove()
                print(f"Removed container: {self.container_name}")
            except Exception as e:
                print(f"Error with container operations: {e}")

        self.client.images.remove(self.image_tag, force=True)
        shutil.rmtree(self.workdir, ignore_errors=True)

    def verify_uploaded_files(self):
        """Verify that all files and subdirectories from data_dir are in /app inside the container."""
        # Get list of files inside container
        exec_log = self.container.exec_run("find /app", demux=True)
        stdout, stderr = exec_log.output
        container_paths = (stdout or b"").decode().strip().splitlines()

        # Normalize paths (strip /app prefix)
        container_relative_paths = [
            path[len("/app/") :] if path.startswith("/app/") else path
            for path in container_paths
            if path != "/app"
        ]

        # Get corresponding local paths from data_dir
        local_paths = []
        for root, _, files in os.walk(self.data_dir):
            for file in files:
                full_path = os.path.join(root, file)
                rel_path = os.path.relpath(full_path, self.data_dir)
                local_paths.append(rel_path)

        # Optionally compare
        missing = [p for p in local_paths if p not in container_relative_paths]
        missing = [m for m in missing if "__pycache__" not in m]  # Exclude __pycache__

        if missing:
            print("❌ Missing files in container:")
            for m in missing:
                print("  -", m)
        else:
            print("✅ All files verified in container.")

        # check if file metrics.py exists in the container
        res = self.run_command("ls")
        print("Files in container:", res.strip().split("\n"))
        if "metrics.py" not in res:
            raise FileNotFoundError(
                "metrics.py not found in the container. Please upload it."
            )
        print("✅ metrics.py found in the container.")

        return container_relative_paths


# Example usage
if __name__ == "__main__":
    runner = PersistentDockerRunner()
    try:
        runner.start()
        runner.verify_uploaded_files()
        # Upload a file to the container
        code_content = """
import backtrader as bt


class MyStrategy(bt.Strategy):
    params = dict(
        short_window=5,  # Period for short-term SMA
        long_window=20,  # Period for long-term SMA
    )

    def __init__(self):
        self.sma_short = bt.ind.SMA(period=self.p.short_window)
        self.sma_long = bt.ind.SMA(period=self.p.long_window)

    def next(self):
        if self.position:
            if self.sma_short < self.sma_long:
                self.close()  # Exit position
        else:
            if self.sma_short > self.sma_long:
                self.buy()  # Enter long position
"""
        # runner.upload_file(code_content, "strategies/test_strategy.py")

        # # run command
        # print("Running command in the container...")
        # output = runner.run_command(
        #     "python metrics.py --strategy-path 'strategies/test_strategy.py' --result-path 'logs/test-res.json'"
        # )

        # print("Command output:", output)

        # # Download the result file
        # result_content = runner.download_file("logs/test-res.json")
        # # save it locally
        # with open("test-res.json", "w") as f:
        #     f.write(result_content)

        # print("Running code in the container...")
        # # read content from "test.py" file
        # with open("test.py", "r") as file:
        #     code_content = file.read()
        # output2 = runner.run_code(code_content)
        # print("Output 2:", output2)

        # get "test.json" from docker container
        # container_files = (
        #     runner.container.exec_run("ls /app").output.decode().strip().split("\n")
        # )
        # if "test.json" in container_files:
        #     print("test.json found in the container.")
        #     exec_log = runner.container.exec_run("cat /app/test.json")
        #     print("Content of test.json:", exec_log.output.decode())
        # else:
        #     print("test.json not found in the container.")
    except Exception as e:
        print(f"An error occurred: {e}")
    finally:
        # runner.verify_uploaded_files()
        runner.stop()
        print("Stopping and cleaning up the container...")
