#!/usr/bin/env python3
"""yt-dlp Workbench - Local GUI Backend Server"""

import json
import os
import re
import signal
import subprocess
import sys
import threading
import time
import uuid
from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler
from pathlib import Path
from urllib.parse import urlparse, parse_qs

# --- Config ---
YTDLP_EXE = r"D:\yt-dlp\yt-dlp\yt-dlp.exe"
GUI_DIR = Path(__file__).resolve().parent
STATIC_DIR = GUI_DIR / "static"
HOST = "127.0.0.1"
PORT = 18080
DEFAULT_DOWNLOAD_DIR = str(Path.home() / "Downloads")

# --- Task Manager ---
tasks: dict[str, dict] = {}
tasks_lock = threading.Lock()


def sanitize_path(p: str) -> str:
    return os.path.normpath(os.path.expandvars(os.path.expanduser(p)))


class WorkbenchHandler(SimpleHTTPRequestHandler):
    """Custom handler with API routing and SSE support."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(STATIC_DIR), **kwargs)

    def log_message(self, format, *args):
        # Quiet logging
        pass

    def end_headers(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        super().end_headers()

    def do_OPTIONS(self):
        self.send_response(204)
        self.end_headers()

    def do_GET(self):
        parsed = urlparse(self.path)

        if parsed.path == "/api/progress":
            qs = parse_qs(parsed.query)
            task_id = qs.get("id", [None])[0]
            if task_id and task_id in tasks:
                self._handle_sse_progress(task_id)
            else:
                self.send_json_error(404, "Task not found")
            return

        if parsed.path == "/api/version":
            self.send_json(self._get_version())
            return

        if parsed.path == "/api/extractors":
            self._handle_extractors()
            return

        if parsed.path == "/api/browse-folder":
            self._handle_browse_folder()
            return

        # Serve static files
        super().do_GET()

    def do_POST(self):
        parsed = urlparse(self.path)
        body = self._read_body()

        if parsed.path == "/api/parse":
            self._handle_parse(body)
            return

        if parsed.path == "/api/download":
            self._handle_download(body)
            return

        if parsed.path == "/api/cancel":
            self._handle_cancel(body)
            return

        self.send_json_error(404, "Endpoint not found")

    def _read_body(self) -> dict:
        length = int(self.headers.get("Content-Length", 0))
        if length == 0:
            return {}
        raw = self.rfile.read(length)
        return json.loads(raw)

    def _get_version(self) -> dict:
        try:
            r = subprocess.run([YTDLP_EXE, "--version"], capture_output=True, text=True, timeout=10)
            return {"version": r.stdout.strip(), "ok": True}
        except Exception as e:
            return {"version": "unknown", "error": str(e), "ok": False}

    def _handle_extractors(self):
        try:
            r = subprocess.run([YTDLP_EXE, "--list-extractors"], capture_output=True, text=True, timeout=15)
            lines = [l.strip() for l in r.stdout.strip().splitlines() if l.strip() and not l.strip().startswith("[")]
            self.send_json({"extractors": lines, "count": len(lines), "ok": True})
        except Exception as e:
            self.send_json_error(500, str(e))

    def _handle_browse_folder(self):
        try:
            ps_cmd = '''
$shell = New-Object -ComObject Shell.Application
$folder = $shell.BrowseForFolder(0, "\u9009\u62e9\u8f93\u51fa\u76ee\u5f55", 0, 0)
if ($folder) { $folder.Self.Path } else { "CANCELLED" }
'''
            r = subprocess.run(
                ["powershell.exe", "-NoProfile", "-Command", ps_cmd],
                capture_output=True, text=True, timeout=120
            )
            result = r.stdout.strip()
            if result == "CANCELLED" or not result:
                self.send_json({"ok": True, "cancelled": True, "path": ""})
            else:
                self.send_json({"ok": True, "cancelled": False, "path": result})
        except Exception as e:
            self.send_json_error(500, str(e))

    def _handle_parse(self, body: dict):
        url = body.get("url", "").strip()
        if not url:
            self.send_json_error(400, "URL is required")
            return

        try:
            cmd = [YTDLP_EXE, "--dump-json", "--no-playlist"]
            flat = body.get("flat", True)
            if flat:
                cmd.insert(2, "--flat-playlist")
            # Network options
            proxy = body.get("proxy")
            if proxy:
                cmd.extend(["--proxy", proxy])
            cookies = body.get("cookies")
            if cookies:
                cmd.extend(["--cookies", cookies])
            cookies_from_browser = body.get("cookies_from_browser")
            if cookies_from_browser:
                cmd.extend(["--cookies-from-browser", cookies_from_browser])
            # Verbose for better error diagnostics
            cmd.insert(1, "--verbose")
            cmd.append(url)

            r = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
            if r.returncode != 0:
                err_msg = r.stderr.strip() or "Failed to parse URL"
                self.send_json_error(400, err_msg[:500], {"stderr_full": err_msg})
                return

            info = json.loads(r.stdout)
            result = self._format_info(info, flat)
            result["ok"] = True
            self.send_json(result)
        except subprocess.TimeoutExpired:
            self.send_json_error(408, "Parse timed out")
        except json.JSONDecodeError:
            self.send_json_error(500, "Invalid response from yt-dlp")
        except Exception as e:
            self.send_json_error(500, str(e))

    def _format_info(self, info: dict, flat: bool) -> dict:
        result = {
            "id": info.get("id", ""),
            "title": info.get("title", "Unknown"),
            "extractor": info.get("extractor", ""),
            "extractor_key": info.get("extractor_key", ""),
            "webpage_url": info.get("webpage_url", ""),
            "thumbnail": info.get("thumbnail", ""),
            "description": (info.get("description", "") or "")[:500],
            "uploader": info.get("uploader", "") or info.get("channel", ""),
            "duration": info.get("duration"),
            "duration_string": info.get("duration_string", ""),
            "view_count": info.get("view_count"),
            "like_count": info.get("like_count"),
            "is_live": info.get("is_live", False),
            "age_limit": info.get("age_limit", 0),
        }

        if flat and info.get("url"):
            result["type"] = "playlist" if info.get("_type") == "playlist" else "video"
            return result

        formats = info.get("formats", [])
        parsed_formats = []
        seen_ids = set()
        for f in formats:
            fid = f.get("format_id", "")
            if fid in seen_ids:
                continue
            seen_ids.add(fid)

            resolution = f.get("resolution") or (f"{f.get('width','?')}x{f.get('height','?')}" if f.get("height") else None)
            parsed_formats.append({
                "format_id": fid,
                "ext": f.get("ext", "?"),
                "resolution": resolution,
                "fps": f.get("fps"),
                "filesize": f.get("filesize") or f.get("filesize_approx"),
                "tbr": f.get("tbr"),
                "vcodec": f.get("vcodec", "none"),
                "acodec": f.get("acodec", "none"),
                "format_note": f.get("format_note", ""),
                "width": f.get("width"),
                "height": f.get("height"),
                "audio_channels": f.get("audio_channels"),
                "abr": f.get("abr"),
            })

        # Sort: video with resolution desc, then audio-only
        video_fmts = [f for f in parsed_formats if f["vcodec"] != "none"]
        audio_fmts = [f for f in parsed_formats if f["vcodec"] == "none" and f["acodec"] != "none"]
        video_fmts.sort(key=lambda x: (x["height"] or 0), reverse=True)
        audio_fmts.sort(key=lambda x: (x["abr"] or 0), reverse=True)

        result["formats"] = video_fmts + audio_fmts
        result["format_count"] = len(parsed_formats)
        result["type"] = "video"
        return result

    def _handle_download(self, body: dict):
        url = body.get("url", "").strip()
        if not url:
            self.send_json_error(400, "URL is required")
            return

        task_id = str(uuid.uuid4())[:8]
        out_dir = sanitize_path(body.get("out_dir", DEFAULT_DOWNLOAD_DIR))

        cmd = [YTDLP_EXE]
        cmd.extend(["--newline", "--progress", "--progress-template", "%(progress._percent_str)s|%(progress._speed_str)s|%(progress._eta_str)s|%(progress.downloaded_bytes)s|%(progress.total_bytes)s|%(progress.total_bytes_estimate)s"])

        # Format selection
        fmt = body.get("format")
        if fmt:
            cmd.extend(["-f", fmt])
        else:
            cmd.extend(["-f", "bestvideo+bestaudio/best"])

        # Output template
        out_tmpl = body.get("output_template", "%(title)s.%(ext)s")
        cmd.extend(["-o", str(Path(out_dir) / out_tmpl)])

        # Audio extraction
        if body.get("extract_audio"):
            cmd.append("-x")
            af = body.get("audio_format", "mp3")
            cmd.extend(["--audio-format", af])

        # Audio quality
        aq = body.get("audio_quality")
        if aq:
            cmd.extend(["--audio-quality", str(aq)])

        # Video quality
        sq = body.get("sort_quality")
        if sq:
            cmd.extend(["-S", sq])

        # Subtitles
        if body.get("write_subs"):
            cmd.append("--write-subs")
        if body.get("write_auto_subs"):
            cmd.append("--write-auto-subs")
        sub_lang = body.get("sub_lang")
        if sub_lang:
            cmd.extend(["--sub-langs", sub_lang])
        if body.get("embed_subs"):
            cmd.append("--embed-subs")

        # Playlist
        playlist_start = body.get("playlist_start")
        if playlist_start is not None:
            cmd.extend(["--playlist-start", str(playlist_start)])
        playlist_end = body.get("playlist_end")
        if playlist_end is not None:
            cmd.extend(["--playlist-end", str(playlist_end)])
        if body.get("playlist_random"):
            cmd.append("--playlist-random")
        if body.get("playlist_reverse"):
            cmd.append("--playlist-reverse")

        # Network
        proxy = body.get("proxy")
        if proxy:
            cmd.extend(["--proxy", proxy])
        cookies = body.get("cookies")
        if cookies:
            cmd.extend(["--cookies", cookies])
        cookies_from_browser = body.get("cookies_from_browser")
        if cookies_from_browser:
            cmd.extend(["--cookies-from-browser", cookies_from_browser])
        rate_limit = body.get("rate_limit")
        if rate_limit:
            cmd.extend(["-r", str(rate_limit)])
        retries = body.get("retries")
        if retries is not None:
            cmd.extend(["-R", str(retries)])

        # Post-processing
        if body.get("embed_thumbnail"):
            cmd.append("--embed-thumbnail")
        if body.get("embed_metadata"):
            cmd.append("--embed-metadata")
        if body.get("write_thumbnail"):
            cmd.append("--write-thumbnail")

        # SponsorBlock
        sb_mark = body.get("sponsorblock_mark")
        if sb_mark:
            cmd.extend(["--sponsorblock-mark", sb_mark])
        sb_remove = body.get("sponsorblock_remove")
        if sb_remove:
            cmd.extend(["--sponsorblock-remove", sb_remove])

        # Filters
        date_after = body.get("dateafter")
        if date_after:
            cmd.extend(["--dateafter", date_after])
        date_before = body.get("datebefore")
        if date_before:
            cmd.extend(["--datebefore", date_before])
        min_filesize = body.get("min_filesize")
        if min_filesize:
            cmd.extend(["--min-filesize", str(min_filesize)])
        max_filesize = body.get("max_filesize")
        if max_filesize:
            cmd.extend(["--max-filesize", str(max_filesize)])
        min_duration = body.get("min_duration")
        if min_duration is not None:
            cmd.extend(["--match-filter", f"duration >= {min_duration}"])
        max_duration = body.get("max_duration")
        if max_duration is not None:
            cmd.extend(["--match-filter", f"duration <= {max_duration}"])

        # Username/password
        username = body.get("username")
        if username:
            cmd.extend(["-u", username])
        password = body.get("password")
        if password:
            cmd.extend(["-p", password])

        # Merge output format
        merge = body.get("merge_output_format")
        if merge:
            cmd.extend(["--merge-output-format", merge])

        # Remux video
        remux = body.get("remux_video")
        if remux:
            cmd.extend(["--remux-video", remux])

        # Concurrent fragments
        cf = body.get("concurrent_fragments")
        if cf is not None:
            cmd.extend(["-N", str(cf)])

        # Ignore errors
        if body.get("ignore_errors"):
            cmd.append("-i")

        cmd.append(url)

        # Ensure output directory exists
        os.makedirs(out_dir, exist_ok=True)

        task = {
            "id": task_id,
            "url": url,
            "title": body.get("title", url),
            "status": "starting",
            "progress": 0,
            "speed": "",
            "eta": "",
            "downloaded": "0",
            "total": "?",
            "cmd": cmd,
            "process": None,
            "output_lines": [],
            "created": time.time(),
        }

        with tasks_lock:
            tasks[task_id] = task

        def run_download():
            try:
                task["status"] = "downloading"
                proc = subprocess.Popen(
                    cmd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                    bufsize=1,
                    creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0,
                )
                task["process"] = proc

                for line in proc.stdout:
                    line = line.rstrip()
                    task["output_lines"].append(line)
                    # Keep only last 500 lines
                    if len(task["output_lines"]) > 500:
                        task["output_lines"] = task["output_lines"][-500:]

                    # Parse progress template output
                    if "|" in line and line.count("|") >= 5:
                        parts = line.split("|")
                        try:
                            task["progress"] = float(parts[0].replace("%", "").strip() or 0)
                            task["speed"] = parts[1].strip()
                            task["eta"] = parts[2].strip()
                            task["downloaded"] = parts[3].strip()
                            task["total"] = parts[4].strip() or parts[5].strip()
                        except (ValueError, IndexError):
                            pass

                    # Detect download completion
                    if "has already been downloaded" in line or "Merging formats into" in line:
                        task["progress"] = 100

                proc.wait()
                if proc.returncode == 0:
                    if task["progress"] < 100:
                        task["progress"] = 100
                    task["status"] = "completed"
                elif task["status"] == "cancelling":
                    task["status"] = "cancelled"
                else:
                    task["status"] = "error"
            except Exception as e:
                task["status"] = "error"
                task["output_lines"].append(f"[ERROR] {e}")
            finally:
                task["process"] = None

        thread = threading.Thread(target=run_download, daemon=True)
        thread.start()

        self.send_json({"ok": True, "task_id": task_id})

    def _handle_cancel(self, body: dict):
        task_id = body.get("task_id", "")
        with tasks_lock:
            task = tasks.get(task_id)

        if not task:
            self.send_json_error(404, "Task not found")
            return

        if task["status"] in ("completed", "cancelled", "error"):
            self.send_json({"ok": True, "already_finished": True})
            return

        task["status"] = "cancelling"
        if task["process"] and task["process"].poll() is None:
            task["process"].terminate()
        self.send_json({"ok": True})

    def _handle_sse_progress(self, task_id: str):
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Connection", "keep-alive")
        self.end_headers()

        last_output_len = 0
        try:
            while True:
                with tasks_lock:
                    task = tasks.get(task_id)

                if not task:
                    self.wfile.write(f"event: error\r\ndata: {json.dumps({'error': 'Task not found'})}\n\n".encode())
                    self.wfile.flush()
                    break

                # Send new output lines
                output_lines = task.get("output_lines", [])
                new_lines = output_lines[last_output_len:]
                for line in new_lines:
                    self.wfile.write(f"data: {json.dumps({'line': line})}\r\n\r\n".encode())
                last_output_len = len(output_lines)

                # Send status update
                status_data = {
                    "status": task["status"],
                    "progress": task["progress"],
                    "speed": task["speed"],
                    "eta": task["eta"],
                    "downloaded": task["downloaded"],
                    "total": task["total"],
                }
                self.wfile.write(f"event: status\r\ndata: {json.dumps(status_data)}\n\n".encode())
                self.wfile.flush()

                if task["status"] in ("completed", "cancelled", "error"):
                    break

                time.sleep(0.5)
        except (BrokenPipeError, ConnectionResetError, OSError):
            pass

    def send_json(self, data: dict):
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps(data, ensure_ascii=False).encode())

    def send_json_error(self, code: int, message: str, extra: dict | None = None):
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        data = {"ok": False, "error": message}
        if extra:
            data.update(extra)
        self.wfile.write(json.dumps(data, ensure_ascii=False).encode())


def cleanup_tasks():
    """Kill all running download processes on shutdown."""
    with tasks_lock:
        for task in tasks.values():
            proc = task.get("process")
            if proc and proc.poll() is None:
                proc.terminate()


def main():
    signal.signal(signal.SIGINT, lambda *_: (cleanup_tasks(), sys.exit(0)))
    signal.signal(signal.SIGTERM, lambda *_: (cleanup_tasks(), sys.exit(0)))

    server = ThreadingHTTPServer((HOST, PORT), WorkbenchHandler)
    print(f"yt-dlp Workbench\r\n  Server: http://{HOST}:{PORT}\r\n  yt-dlp: {YTDLP_EXE}\r\n  Output: {DEFAULT_DOWNLOAD_DIR}")

    import webbrowser
    threading.Timer(0.8, lambda: webbrowser.open(f"http://{HOST}:{PORT}")).start()

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        cleanup_tasks()
        server.server_close()
        print("\r\nShutdown complete.")


if __name__ == "__main__":
    main()
