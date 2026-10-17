import re

with open("c:/Users/tyert/OneDrive/Desktop/inoagent site/jars/fabric-api-0.161.0-26.2.jar", "r", encoding="utf-8", errors="ignore") as f:
    text = f.read()

title_m = re.search(r"<title>(.*?)</title>", text)
print("Title:", title_m.group(1) if title_m else "No title")

urls = re.findall(r"https://[^\s\"'<>]+", text)
print(f"Found {len(urls)} URLs")
for u in urls:
    if any(k in u for k in ["download", "fabric", "previews", "content.dropbox", "uc?"]):
        print("MATCH:", u)
