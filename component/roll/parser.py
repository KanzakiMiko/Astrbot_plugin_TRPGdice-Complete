import re
from dataclasses import dataclass
from typing import Optional


@dataclass
class ParsedInlineCommand:
    cmd: str
    expr: str = ""
    remark: Optional[str] = None
    skill_value: Optional[str] = ""
    dice_count: str = "1"
    roll_times: str = "1"


def strip_command_prefix(message: str, prefixes: list[str]) -> Optional[str]:
    if not any(message.startswith(prefix) for prefix in prefixes):
        return None
    return re.sub(r"\s+", "", message[1:])


def _split_skill_and_value(expr: str) -> tuple[str, Optional[str]]:
    expr = expr.strip()
    if not expr:
        return "", None

    explicit_with_modifier = re.match(r"^(.+?)(\d+)([+-]\d+)$", expr)
    if explicit_with_modifier:
        name = explicit_with_modifier.group(1) + explicit_with_modifier.group(3)
        return name.strip(), explicit_with_modifier.group(2)

    if re.match(r"^.+[+-]\d+$", expr):
        return expr, None

    value_match = re.search(r"(\d+)$", expr)
    if value_match:
        value = value_match.group(1)
        name = expr[:-len(value)].strip()
        return (name or value), value

    return expr, None


def _parse_check_command(message: str, prefix: str) -> ParsedInlineCommand:
    body = message[len(prefix):]
    roll_times = "1"
    dice_count = "0"
    cmd = prefix

    hash_match = re.match(r"^(\d+)#(.+)", body)
    if hash_match:
        roll_times = hash_match.group(1)
        body = hash_match.group(2)

    if prefix in {"ra", "rc"}:
        if body.startswith("b"):
            cmd = "rab"
            body = body[1:]
        elif body.startswith("p"):
            cmd = "rap"
            body = body[1:]

    if prefix in {"rav", "rcv"}:
        return ParsedInlineCommand(cmd=cmd, expr=body.strip(), roll_times=roll_times)

    pure_number = False
    if cmd in {"rab", "rap"}:
        body = body.strip()
        if "c" in body:
            parts = body.split("c", 1)
            dice_count = parts[0].strip() or "1"
            body = parts[1].strip()
            pure_number = body.isdigit()
        elif body.isdigit():
            dice_count = "1"
            pure_number = True
        else:
            dice_match = re.match(r"^(\d+)", body)
            if dice_match:
                matched_num = dice_match.group(1)
                remaining = body[len(matched_num):].strip()
                if not remaining:
                    dice_count = "1"
                    pure_number = True
                    body = matched_num
                else:
                    dice_count = matched_num
                    body = remaining
            else:
                dice_count = "1"

    skill_name, skill_value = _split_skill_and_value(body)
    if pure_number:
        skill_value = skill_value or body
        skill_name = skill_name or str(skill_value)

    return ParsedInlineCommand(
        cmd=cmd,
        expr=skill_name.strip(),
        skill_value=skill_value,
        dice_count=dice_count,
        roll_times=roll_times,
    )


_ADV_TERM = r"[+\-*/](?:\d*d\d+|\d+)"


def _parse_adv_expr(raw: str):
    """优势/劣势写法 -> (表达式, 备注);不是优势写法返回 None。

    支持 adv/dis/优势/劣势,可带重复次数前缀和可选的 d:
    "优势+6"、"d优势+6"、"3#d优势+6"、"劣势d12-1"、"3#adv+2"。
    """
    m = re.match(
        r"(?:(?P<n>\d+)#)?d?"
        r"(?:(?P<a>adv|dis)(?:d(?P<f1>\d+))?(?![A-Za-z])|(?P<c>优势|劣势)(?:d(?P<f2>\d+))?)"
        r"(?P<mod>(?:" + _ADV_TERM + r")*)",
        raw,
        re.IGNORECASE,
    )
    if not m:
        return None
    is_adv = (m.group("a") or "").lower() == "adv" or m.group("c") == "优势"
    faces = m.group("f1") or m.group("f2") or "20"
    prefix = f"{m.group('n')}#" if m.group("n") else ""
    expr = f"{prefix}2d{faces}k{'h' if is_adv else 'l'}1{m.group('mod')}"
    return expr, (raw[m.end():].strip() or None)


def parse_inline_command(message: str) -> Optional[ParsedInlineCommand]:
    """Parse dot-style inline commands handled by identify_command."""
    m = re.match(r"^([a-z]+)", message, re.I)
    if not m:
        return None

    cmd = m.group(1).lower()
    expr = message[m.end():].strip()
    remark = None
    skill_value: Optional[str] = ""
    dice_count = "1"
    roll_times = "1"

    if cmd[0:2] == "en":
        sv_match = re.search(r"\d+$", message)
        if sv_match:
            skill_value = sv_match.group()
            expr = message[2:len(message) - len(skill_value)]
        else:
            skill_value = None
            expr = message[2:]
        cmd = "en"

    # ".r adv" 粘连成 "radv"(会被当成 ra 技能检定)、".r 优势" 成 "r优势":改写成 rd 再解析
    if re.match(r"^r(?:adv|dis)(?:d\d+)?(?![a-z])", message, re.I) or re.match(r"^r(?:优势|劣势)", message):
        return parse_inline_command("rd" + message[1:])

    if cmd == "rau":
        return _parse_check_command(message, "rau")

    if cmd == "rb":
        return _parse_check_command(f"rab{message[2:]}", "ra")

    if cmd == "rp":
        return _parse_check_command(f"rap{message[2:]}", "ra")

    if cmd == "hl":
        return _parse_check_command(f"rah{message[2:]}", "rah")

    if cmd in {"rah", "rch", "rav", "rcv"}:
        return _parse_check_command(message, cmd)

    if cmd[0:2] in {"ra", "rc"}:
        return _parse_check_command(message, cmd[0:2])

    elif cmd == "ri":
        expr = message[2:].strip()

    elif cmd[0:2] == "rd":
        raw = message[2:].strip()
        # 完整骰式(".rd 1d100 试骰" 粘连成 "rd1d100试骰"):先吃整个 XdY,
        # 否则旧逻辑会把 "1d100" 拆成骰面 1 + 备注 "d100试骰",变成掷 1d1
        term = r"[+\-*/](?:\d*d\d+|\d+)"
        mod_re = r"((?:" + term + r")*)"
        adv_parsed = _parse_adv_expr(raw)
        if adv_parsed:
            return ParsedInlineCommand(
                cmd="rd", expr=adv_parsed[0], remark=adv_parsed[1], skill_value=skill_value,
                dice_count=dice_count, roll_times=roll_times,
            )
        adv_match = re.match(
            r"(?:(?P<a>adv|dis)(?:d(?P<f1>\d+))?(?![A-Za-z])|(?P<c>优势|劣势)(?:d(?P<f2>\d+))?)"
            r"(?P<mod>(?:" + term + r")*)",
            raw,
            re.IGNORECASE,
        )
        if adv_match:
            is_adv = (adv_match.group("a") or "").lower() == "adv" or adv_match.group("c") == "优势"
            faces = adv_match.group("f1") or adv_match.group("f2") or "20"
            expr = f"2d{faces}k{'h' if is_adv else 'l'}1{adv_match.group('mod')}"
            remark = raw[adv_match.end():].strip() or None
            cmd = "rd"
            return ParsedInlineCommand(
                cmd=cmd, expr=expr, remark=remark, skill_value=skill_value,
                dice_count=dice_count, roll_times=roll_times,
            )
        expr_match = re.match(r"(\d*d\d+)" + mod_re, raw, re.IGNORECASE)
        if expr_match:
            expr = expr_match.group(0)
            remark = raw[len(expr):].strip() or None
        else:
            dice_match = re.match(r"(\d+)" + mod_re, raw, re.IGNORECASE)
            if dice_match:
                expr = f"1d{dice_match.group(1)}{dice_match.group(2)}"
                remark = raw[dice_match.end():].strip()
            else:
                mod_match = re.match(r"((?:" + term + r")+)", raw, re.IGNORECASE)
                if mod_match:
                    expr = "1d100" + mod_match.group(1)
                    remark = raw[mod_match.end():].strip()
                else:
                    expr = "1d100"
                    remark = raw.strip()
        cmd = "rd"

    elif cmd[0] == "r" and cmd != "rv":
        # rv(吸血鬼骰)注册在指令系统,放行给桥接;这里吞掉会让它永远变成 .r
        is_hidden_roll = cmd == "rh"
        command_len = 2 if is_hidden_roll else 1
        content = message[command_len:].strip()
        if not content:
            expr = "1d100"
            remark = ""
        elif _parse_adv_expr(content):
            expr, remark = _parse_adv_expr(content)
            remark = remark or ""
        else:
            match = re.match(r"([\d#+\-*/().xXdkvbpBP]+)", content, re.IGNORECASE)
            if match:
                expr = match.group(1)
                remark = content[match.end():].strip()
            else:
                expr = "1d100"
                remark = content.strip()
        cmd = "rh" if is_hidden_roll else "r"

    return ParsedInlineCommand(
        cmd=cmd,
        expr=expr,
        remark=remark,
        skill_value=skill_value,
        dice_count=dice_count,
        roll_times=roll_times,
    )
