#!/usr/bin/env python3
"""
Recon Dominicx - Python (Auto-check & Auto-install edition)

Features:
- Fancy DOMINICX banner
- Check required tools: subfinder, httpx, naabu, nmap, katana, dirsearch, nuclei
- Auto-install missing Go-based tools via `go install` (requires `go` available)
- Auto-clone dirsearch if missing
- Attempt package manager install for nmap (apt or brew)
- Run real recon pipeline (subfinder -> httpx -> naabu -> nmap -> dirsearch -> katana -> nuclei)
- Logs errors to outdir/logs/error.log

Usage:
    python3 recon_dominicx_auto.py target.com [--install]

WARNING: This script executes network scans and runs external tools. Only use on targets you are authorized to test.
"""

import argparse
import shutil
import subprocess
import sys
import os
import time
import datetime
import logging
from pathlib import Path
from typing import List

# -------------------- Config --------------------
GO_PACKAGES = {
    'subfinder': 'github.com/projectdiscovery/subfinder/v2/cmd/subfinder@latest',
    'httpx': 'github.com/projectdiscovery/httpx/cmd/httpx@latest',
    'naabu': 'github.com/projectdiscovery/naabu/v2/cmd/naabu@latest',
    'katana': 'github.com/projectdiscovery/katana/cmd/katana@latest',
    'nuclei': 'github.com/projectdiscovery/nuclei/v2/cmd/nuclei@latest',
}
REQUIRED = ['subfinder', 'httpx', 'naabu', 'nmap', 'katana', 'dirsearch', 'nuclei']
THREADS = 40
TIMEOUT = 3600

# -------------------- Logging --------------------
logger = logging.getLogger('dominicx')
logger.setLevel(logging.DEBUG)

# Console colors (fallback no-color)
try:
    from colorama import Fore, Style, init as colorama_init
    colorama_init(autoreset=True)
except Exception:
    class _C:
        RESET_ALL = ''
        RED = ''
        GREEN = ''
        YELLOW = ''
        CYAN = ''
        MAGENTA = ''
    Fore = _C()
    Style = _C()

# -------------------- Utils --------------------

def now_ts():
    return datetime.datetime.utcnow().strftime('%Y-%m-%dT%H:%M:%SZ')


def run(cmd: List[str], cwd: Path = None, timeout: int = TIMEOUT) -> subprocess.CompletedProcess:
    try:
        cp = subprocess.run(cmd, cwd=cwd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=timeout)
        return cp
    except subprocess.TimeoutExpired:
        return subprocess.CompletedProcess(cmd, 124, stdout='', stderr=f'Timeout after {timeout}s')
    except Exception as e:
        return subprocess.CompletedProcess(cmd, 1, stdout='', stderr=str(e))


def which(bin_name: str) -> bool:
    return shutil.which(bin_name) is not None


def write_file(p: Path, data: str):
    p.parent.mkdir(parents=True, exist_ok=True)
    with open(p, 'a') as f:
        f.write(data)

# -------------------- Banner --------------------
DOMINICX_BANNER = r'''
  _    _    _    _    _    _    _    _    _    _    _    _    _    _    _    _    _  
{\o/}{\o/}{\o/}{\o/}{\o/}{\o/}{\o/}{\o/}{\o/}{\o/}{\o/}{\o/}{\o/}{\o/}{\o/}{\o/}{\o/}
 /_\  /_\  /_\  /_\  /_\  /_\  /_\  /_\  /_\  /_\  /_\  /_\  /_\  /_\  /_\  /_\  /_\ 
  _    ██████╗  ██████╗ ███╗   ███╗██╗███╗   ██╗   ██╗ ██████╗██╗  ██╗ ██████╗    _  
{\o/}  ██╔══██╗██╔═══██╗████╗ ████║██║████╗  ██║   ██║██╔════╝╚██╗██╔╝██╔════╝  {\o/}
 /_\   ██║  ██║██║   ██║██╔████╔██║██║██╔██╗ ██║   ██║██║      ╚███╔╝ ██║        /_\ 
  _    ██║  ██║██║   ██║██║╚██╔╝██║██║██║╚██╗██║   ██║██║      ██╔██╗ ██║         _  
{\o/}  ██████╔╝╚██████╔╝██║ ╚═╝ ██║██║██║ ╚████║▄█╗██║╚██████╗██╔╝ ██╗╚██████╗  {\o/}
 /_\   ╚═════╝  ╚═════╝ ╚═╝     ╚═╝╚═╝╚═╝  ╚═══╝╚═╝╚═╝ ╚═════╝╚═╝  ╚═╝ ╚═════╝   /_\ 
  _    _    _    _    _    _    _    _    _    _    _    _    _    _    _    _    _  
{\o/}{\o/}{\o/}{\o/}{\o/}{\o/}{\o/}{\o/}{\o/}{\o/}{\o/}{\o/}{\o/}{\o/}{\o/}{\o/}{\o/}
 /_\  /_\  /_\  /_\  /_\  /_\  /_\  /_\  /_\  /_\  /_\  /_\  /_\  /_\  /_\  /_\  /_\ 

           DOMINICX Recon Framework - Trinitysec - Auto Install Edition
'''

# -------------------- Installer Helpers --------------------

def go_install(pkg: str) -> bool:
    go = shutil.which('go')
    if not go:
        logger.error('go not found; cannot go install %s', pkg)
        return False
    print(Fore.CYAN + f'[ACTION] go install {pkg} ...')
    cp = run(['go', 'install', pkg])
    if cp.returncode == 0:
        print(Fore.GREEN + f'[OK] go install succeeded: {pkg}')
        return True
    else:
        logger.error('go install failed for %s: %s', pkg, cp.stderr)
        print(Fore.RED + f'[ERROR] go install failed for {pkg}')
        return False


def try_pkg_manager_install_nmap() -> bool:
    # Attempt apt, then brew
    print(Fore.CYAN + '[ACTION] Trying package manager install for nmap...')
    if shutil.which('apt'):
        cp = run(['sudo', 'apt', 'update'])
        _ = run(['sudo', 'apt', 'install', '-y', 'nmap'])
        return shutil.which('nmap') is not None
    if shutil.which('brew'):
        run(['brew', 'install', 'nmap'])
        return shutil.which('nmap') is not None
    print(Fore.YELLOW + '[WARN] No supported package manager found for nmap auto-install')
    return False


def clone_dirsearch(outdir: Path) -> bool:
    target = outdir / 'dirsearch'
    if target.exists():
        return True
    print(Fore.CYAN + '[ACTION] Cloning dirsearch...')
    cp = run(['git', 'clone', '--depth', '1', 'https://github.com/maurosoria/dirsearch.git', str(target)])
    if cp.returncode == 0:
        print(Fore.GREEN + '[OK] dirsearch cloned')
        return True
    else:
        logger.error('Failed to clone dirsearch: %s', cp.stderr)
        print(Fore.RED + '[ERROR] git clone dirsearch failed')
        return False

# -------------------- Recon Class --------------------
class ReconAuto:
    def __init__(self, target: str, outdir: Path, do_install: bool = False):
        self.target = target
        self.outdir = outdir
        self.do_install = do_install
        self.logdir = outdir / 'logs'
        self.logdir.mkdir(parents=True, exist_ok=True)
        self.error_log = self.logdir / 'error.log'
        fh = logging.FileHandler(str(self.error_log), encoding='utf-8')
        fh.setLevel(logging.DEBUG)
        fh.setFormatter(logging.Formatter('%(asctime)s %(levelname)s %(message)s'))
        logger.addHandler(fh)

    def check_and_install_all(self) -> bool:
        missing = [t for t in REQUIRED if not which(t)]
        if not missing:
            print(Fore.GREEN + '[OK] All required tools present')
            return True
        print(Fore.YELLOW + '[WARN] Missing tools: ' + ', '.join(missing))
        if not self.do_install:
            print(Fore.RED + '[ERROR] Missing tools. Re-run with --install to attempt auto-install')
            logger.error('Missing tools: %s', ','.join(missing))
            return False
        # Attempt installs
        for m in missing:
            if m in GO_PACKAGES:
                success = go_install(GO_PACKAGES[m])
                if not success:
                    logger.error('Failed go install for %s', m)
                    return False
            elif m == 'nmap':
                success = try_pkg_manager_install_nmap()
                if not success:
                    logger.error('Failed to auto-install nmap')
                    return False
            elif m == 'dirsearch':
                success = clone_dirsearch(self.outdir)
                if not success:
                    return False
            else:
                logger.error('No auto-install rule for %s', m)
                print(Fore.RED + f'[ERROR] No auto-install rule for {m}. Install manually.')
                return False
        # Re-check
        still = [t for t in REQUIRED if not which(t)]
        if still:
            print(Fore.RED + '[ERROR] Some tools still missing after install: ' + ', '.join(still))
            logger.error('Tools still missing: %s', ','.join(still))
            return False
        print(Fore.GREEN + '[OK] All tools installed and available')
        return True

    # Step 1: subfinder + passive sources
    def step_subenum(self):
        print(Fore.CYAN + '\n[STEP 1] Subdomain Enumeration...')
        subfinder_out = self.outdir / 'subfinder.txt'
        run(['subfinder', '-d', self.target, '-silent', '-o', str(subfinder_out)])
        # crt.sh
        crt_out = self.outdir / 'crtsh.txt'
        cp = run(['curl', '-s', f'https://crt.sh/?q=%25.{self.target}&output=json'])
        if cp.returncode == 0 and cp.stdout:
            try:
                import json
                arr = json.loads(cp.stdout)
                with open(crt_out, 'w') as fh:
                    for item in arr:
                        nv = item.get('name_value')
                        if nv:
                            fh.write(nv.replace('*.', '') + '\n')
            except Exception as e:
                logger.exception('crt.sh parse')
        # urlscan
        urlscan_out = self.outdir / 'urlscan.txt'
        cp = run(['curl', '-s', f'https://urlscan.io/api/v1/search/?q=domain:{self.target}&size=10000'])
        if cp.returncode == 0 and cp.stdout:
            try:
                import json
                data = json.loads(cp.stdout)
                with open(urlscan_out, 'w') as fh:
                    for r in data.get('results', []):
                        domain = r.get('page', {}).get('domain')
                        if domain:
                            fh.write(domain + '\n')
            except Exception:
                logger.exception('urlscan parse')
        # webarchive
        web_out = self.outdir / 'webarchive.txt'
        cp = run(['curl', '-s', f'http://web.archive.org/cdx/search/cdx?url=*.{self.target}/*&output=json&collapse=urlkey'])
        if cp.returncode == 0 and cp.stdout:
            try:
                import json, re
                arr = json.loads(cp.stdout)
                with open(web_out, 'w') as fh:
                    for row in arr[1:]:
                        url = row[2]
                        m = re.search(r'([a-zA-Z0-9._-]+\.)?'+re.escape(self.target), url)
                        if m:
                            fh.write(m.group(0) + '\n')
            except Exception:
                logger.exception('webarchive parse')
        # merge
        all_files = [subfinder_out, crt_out, urlscan_out, web_out]
        merged = set()
        for f in all_files:
            if f.exists():
                with open(f, 'r') as fh:
                    for line in fh:
                        line = line.strip()
                        if line:
                            merged.add(line)
        subs_all = self.outdir / 'subs_all.txt'
        with open(subs_all, 'w') as fh:
            for s in sorted(merged):
                fh.write(s + '\n')
        print(Fore.GREEN + f'[OK] Subdomain enumeration done ({len(merged)} hosts)')

    # Step 2: httpx
    def step_alive(self):
        print(Fore.CYAN + '\n[STEP 2] Alive check (httpx)')
        subs_all = self.outdir / 'subs_all.txt'
        if not subs_all.exists():
            print(Fore.YELLOW + '[WARN] No subdomains file, skipping httpx')
            return
        out_raw = self.outdir / 'httpx_raw.txt'
        run(['httpx', '-l', str(subs_all), '-silent', '-threads', str(THREADS), '-status-code', '-title', '-ip', '-o', str(out_raw)])
        alive = self.outdir / 'alive.txt'
        ip_list = self.outdir / 'ip_list.txt'
        if out_raw.exists():
            with open(out_raw, 'r') as fr, open(alive, 'w') as fa, open(ip_list, 'w') as fi:
                for line in fr:
                    parts = line.strip().split()
                    if not parts:
                        continue
                    url = parts[0]
                    fa.write(url + '\n')
                    if '[' in line and ']' in line:
                        import re
                        m = re.search(r'\[([0-9.]+)\]', line)
                        if m:
                            fi.write(m.group(1) + '\n')
        print(Fore.GREEN + f'[OK] httpx done, alive saved to {alive}')

    # Step 3: naabu + nmap
    def step_ports(self):
        print(Fore.CYAN + '\n[STEP 3] Port scanning (naabu + nmap)')
        ip_list = self.outdir / 'ip_list.txt'
        if not ip_list.exists() or ip_list.stat().st_size == 0:
            print(Fore.YELLOW + '[WARN] No IPs for naabu, skipping')
            return
        open_raw = self.outdir / 'open_ports_raw.txt'
        run(['naabu', '-list', str(ip_list), '-o', str(open_raw), '-silent'])
        if open_raw.exists():
            shutil.copyfile(open_raw, self.outdir / 'open_ports.txt')
        # quick nmap
        try:
            with open(self.outdir / 'open_ports.txt', 'r') as fh:
                for i, line in enumerate(fh):
                    if i >= 30:
                        break
                    if ':' in line:
                        host, port = line.strip().split(':', 1)
                        nmap_out = self.outdir / f'nmap_{host}_{port}.txt'
                        run(['nmap', '-sV', '-p', port, host, '-oN', str(nmap_out)])
        except Exception:
            logger.exception('nmap quick scan error')
        print(Fore.GREEN + '[OK] Port scan done')

    # Step 4: dirsearch + katana
    def step_content(self):
        print(Fore.CYAN + '\n[STEP 4] Content discovery (dirsearch + katana)')
        alive = self.outdir / 'alive.txt'
        if not alive.exists():
            print(Fore.YELLOW + '[WARN] No alive hosts, skipping content discovery')
            return
        dir_out = self.outdir / 'dirsearch_out'
        dir_out.mkdir(exist_ok=True)
        kat_out = self.outdir / 'katana_out'
        kat_out.mkdir(exist_ok=True)
        dirsearch_path = self.outdir / 'dirsearch' / 'dirsearch.py'
        with open(alive, 'r') as fh:
            for line in fh:
                url = line.strip()
                if not url:
                    continue
                name = url.replace('://', '_').replace('/', '_')
                if dirsearch_path.exists():
                    run(['python3', str(dirsearch_path), '-u', url, '-x', '403,404,500,400,502,503,429', '--random-agent', '-e', 'php,js,html', '-o', str(dir_out / f'{name}.txt')])
                else:
                    logger.info('dirsearch not present')
                if which('katana'):
                    run(['katana', '-u', url, '-o', str(kat_out / f'{name}.txt')])
        # merge dirsearch
        merged_paths = self.outdir / 'dirs.txt'
        with open(merged_paths, 'w') as outf:
            for f in dir_out.glob('*.txt'):
                try:
                    with open(f, 'r') as rf:
                        for l in rf:
                            outf.write(l)
                except Exception:
                    pass
        print(Fore.GREEN + f'[OK] Content discovery done, paths in {merged_paths}')

    # Step 5: nuclei
    def step_nuclei(self):
        print(Fore.CYAN + '\n[STEP 5] Nuclei scanning')
        alive = self.outdir / 'alive.txt'
        if not alive.exists():
            print(Fore.YELLOW + '[WARN] No alive hosts, skipping nuclei')
            return
        if which('nuclei'):
            run(['nuclei', '-l', str(alive), '-rl', '10', '-bs', '2', '-c', '2', '-as', '-severity', 'critical,high,medium', '-o', str(self.outdir / 'nuclei_results.txt')])
            print(Fore.GREEN + '[OK] nuclei done')
        else:
            print(Fore.YELLOW + '[WARN] nuclei not installed, skipping')

    def generate_summary(self):
        print(Fore.CYAN + '\n[SUMMARY] Generating summary.json')
        subs_count = 0
        alive_count = 0
        ports_count = 0
        try:
            if (self.outdir / 'subs_all.txt').exists():
                subs_count = sum(1 for _ in open(self.outdir / 'subs_all.txt'))
            if (self.outdir / 'alive.txt').exists():
                alive_count = sum(1 for _ in open(self.outdir / 'alive.txt'))
            if (self.outdir / 'open_ports.txt').exists():
                ports_count = sum(1 for _ in open(self.outdir / 'open_ports.txt'))
            import json
            summary = {'target': self.target, 'scanned_at': now_ts(), 'stats': {'subdomains': subs_count, 'alive': alive_count, 'open_ports': ports_count}}
            with open(self.outdir / 'summary.json', 'w') as fh:
                json.dump(summary, fh, indent=2)
            print(Fore.GREEN + '[OK] summary.json created')
        except Exception:
            logger.exception('summary error')

    def run(self):
        print(Fore.MAGENTA + DOMINICX_BANNER)
        print(Fore.YELLOW + f'[INFO] Target: {self.target}  Outdir: {self.outdir}')
        ok = self.check_and_install_all()
        if not ok:
            print(Fore.RED + '[ERROR] Pre-checks failed. See logs for details.')
            return
        try:
            self.step_subenum()
            self.step_alive()
            self.step_ports()
            self.step_content()
            self.step_nuclei()
            self.generate_summary()
        except KeyboardInterrupt:
            print(Fore.RED + '\n[ABORT] Interrupted by user')
        except Exception:
            logger.exception('Unexpected error during run')

# -------------------- Main --------------------

def main():
    parser = argparse.ArgumentParser(description='Recon Dominicx - Auto-install edition')
    parser.add_argument('target', help='Target domain (example.com)')
    parser.add_argument('--install', action='store_true', help='Attempt to auto-install missing tools')
    args = parser.parse_args()

    target = args.target.strip()
    if '/' in target:
        print(Fore.RED + '[ERROR] Please provide a bare domain (example.com)')
        sys.exit(1)

    outdir = Path.cwd() / f'recon_{target}_{datetime.datetime.now().strftime("%Y%m%d_%H%M%S")}'
    outdir.mkdir(parents=True, exist_ok=True)

    # console logger
    ch = logging.StreamHandler()
    ch.setLevel(logging.INFO)
    ch.setFormatter(logging.Formatter('%(asctime)s %(levelname)s %(message)s'))
    logger.addHandler(ch)

    recon = ReconAuto(target, outdir, do_install=args.install)
    recon.run()

if __name__ == '__main__':
    main()
