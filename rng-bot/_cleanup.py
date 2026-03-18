#!/usr/bin/env python3
"""Remove old inline HTML from web_control.py"""

with open("web_control.py", "r") as f:
    lines = f.readlines()

remove_start = None
remove_end = None
for i, line in enumerate(lines):
    if remove_start is None and "<meta charset" in line and i > 140:
        remove_start = i
    if "</html>" in line and '"""' in line:
        remove_end = i + 1

if remove_start is None or remove_end is None:
    print(f"Could not find boundaries: start={remove_start} end={remove_end}")
    exit(1)

print(f"Removing lines {remove_start + 1} to {remove_end} ({remove_end - remove_start} lines)")

while remove_end < len(lines) and lines[remove_end].strip() == "":
    remove_end += 1
if remove_end < len(lines) and "Request Handler" in lines[remove_end]:
    remove_end += 1
    print("Also removing duplicate Request Handler marker")

new_lines = lines[:remove_start] + lines[remove_end:]

with open("web_control.py", "w") as f:
    f.writelines(new_lines)

print(f"Done: {len(lines)} -> {len(new_lines)} lines")
