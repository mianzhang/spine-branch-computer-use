#!/usr/bin/env python3
"""Probe whether an OpenAI-compatible (e.g. vLLM) endpoint can serve as a CUA subagent.

Run this FROM a host that can reach the endpoint (this repo's box currently cannot
reach 10.192.78.158:8000). Checks the four things our CUA harness needs:
  1. reachable + text generation
  2. vision (image_url input)  -- required: CUAs read screenshots
  3. native tool-calling (tools= + tool_choice)  -- used by cua_provider=chat/qwen
  4. XML-mode fallback (tool described in system prompt)  -- used if (3) unsupported

Usage:
  pip install openai pillow
  python probe_subagent_endpoint.py \
      --base-url http://10.192.78.158:8000/v1 --model qwen3.5-9b [--image some_screenshot.png]
"""
import argparse, base64, io, sys


def _img_b64(path):
    if path:
        return base64.b64encode(open(path, "rb").read()).decode()
    from PIL import Image, ImageDraw
    im = Image.new("RGB", (640, 200), "white")
    ImageDraw.Draw(im).text((20, 90), "Sign in   |   Search: [ flights ]   Book", fill="black")
    buf = io.BytesIO(); im.save(buf, format="PNG")
    return base64.b64encode(buf.getvalue()).decode()


TOOL = {"type": "function", "function": {"name": "computer_use", "description": "control the GUI",
        "parameters": {"type": "object", "required": ["action"], "properties": {
            "action": {"type": "string", "enum": ["left_click", "type", "key", "wait", "terminate"]},
            "coordinate": {"type": "array"}, "text": {"type": "string"}}}}}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--base-url", required=True)
    ap.add_argument("--model", required=True)
    ap.add_argument("--image", default=None, help="a screenshot PNG (optional; a synthetic one is used otherwise)")
    a = ap.parse_args()
    import openai
    c = openai.OpenAI(base_url=a.base_url, api_key="EMPTY", timeout=90)
    b64 = _img_b64(a.image)
    M = a.model
    ok = {}

    try:
        ids = [m.id for m in c.models.list().data]
        print("0) reachable; served:", ids[:5]); ok["reach"] = True
    except Exception as e:
        print("0) UNREACHABLE:", str(e)[:200]); sys.exit(1)

    try:
        r = c.chat.completions.create(model=M, messages=[{"role": "user", "content": "reply OK"}], max_tokens=20)
        print("1) text: OK ->", repr((r.choices[0].message.content or "")[:40])); ok["text"] = True
    except Exception as e:
        print("1) text FAIL:", str(e)[:200])

    try:
        r = c.chat.completions.create(model=M, max_tokens=120, messages=[{"role": "user", "content": [
            {"type": "text", "text": "In one sentence, what UI/site is shown?"},
            {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{b64}"}}]}])
        txt = (r.choices[0].message.content or "")
        print("2) vision: OK ->", repr(txt[:140])); ok["vision"] = bool(txt.strip())
    except Exception as e:
        print("2) vision FAIL (blocker if this fails):", str(e)[:200])

    msgs = [{"role": "system", "content": "Use the computer_use tool for every GUI action."},
            {"role": "user", "content": [{"type": "image_url", "image_url": {"url": f"data:image/png;base64,{b64}"}},
                                          {"type": "text", "text": "Click the Search box. Take the next action."}]}]
    for tc in ("auto", "required"):
        try:
            r = c.chat.completions.create(model=M, messages=msgs, max_tokens=512, tools=[TOOL], tool_choice=tc)
            m = r.choices[0].message
            n = len(m.tool_calls or [])
            print(f"3) native tools tool_choice={tc}: OK | tool_calls={n}",
                  ("| args=" + m.tool_calls[0].function.arguments[:80]) if n else f"| content={repr((m.content or '')[:60])}")
            ok.setdefault("tools", n > 0 or ok.get("tools", False))
        except Exception as e:
            print(f"3) native tools tool_choice={tc}: FAIL", str(e)[:160])

    # 4) XML fallback (no tools param; tool format in system prompt)
    sysx = ("Reply ONLY with a tool call in this exact format:\n"
            "<tool_call>\n<function=computer_use>\n<parameter=action>\nleft_click\n</parameter>\n"
            "<parameter=coordinate>\n[500, 100]\n</parameter>\n</function>\n</tool_call>")
    try:
        r = c.chat.completions.create(model=M, max_tokens=512, messages=[{"role": "system", "content": sysx},
            {"role": "user", "content": [{"type": "image_url", "image_url": {"url": f"data:image/png;base64,{b64}"}},
                                          {"type": "text", "text": "Click the Search box."}]}])
        out = r.choices[0].message.content or ""
        print("4) XML-mode: has <tool_call>?", "<tool_call>" in out, "| out:", repr(out[:120]))
        ok["xml"] = "<tool_call>" in out
    except Exception as e:
        print("4) XML-mode FAIL:", str(e)[:160])

    print("\n=== VERDICT ===")
    vision = ok.get("vision"); acts = ok.get("tools") or ok.get("xml")
    if vision and acts:
        print("USABLE as CUA subagent. Recommended provider:",
              "chat/qwen with native tools" if ok.get("tools") else "chat with XML (native tools OFF)")
    elif not vision:
        print("NOT usable: no working vision (image input) — CUAs must read screenshots.")
    else:
        print("Vision works but no action channel (neither native tools nor parseable XML) — would rely on the harness's retry/parse fallbacks; risky.")


if __name__ == "__main__":
    main()
