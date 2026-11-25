import random
import re
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

from ..common.output import get_output
from ..roll.dice import parse_dice_expression


@dataclass
class InitiativeItem:
    name: str
    init_value: int
    player_id: int


class InitiativeManager:
    """Group-scoped initiative tracker."""

    def __init__(self):
        self._items: Dict[str, List[InitiativeItem]] = {}
        self._current_index: Dict[str, int] = {}

    def _ensure_group(self, group_id: str) -> None:
        self._items.setdefault(str(group_id), [])
        self._current_index.setdefault(str(group_id), -1)

    def add_item(self, group_id: str, item: InitiativeItem) -> None:
        group_id = str(group_id)
        self._ensure_group(group_id)
        self._items[group_id].append(item)
        self.sort_list(group_id)

    def remove_by_name(self, group_id: str, name: str) -> None:
        group_id = str(group_id)
        self._ensure_group(group_id)
        self._items[group_id] = [item for item in self._items[group_id] if item.name != name]
        if not self._items[group_id]:
            self._current_index[group_id] = -1
        elif self._current_index[group_id] >= len(self._items[group_id]):
            self._current_index[group_id] = 0

    def remove_by_player(self, group_id: str, player_id: int) -> None:
        group_id = str(group_id)
        self._ensure_group(group_id)
        self._items[group_id] = [item for item in self._items[group_id] if item.player_id != player_id]
        if not self._items[group_id]:
            self._current_index[group_id] = -1

    def clear(self, group_id: str) -> None:
        group_id = str(group_id)
        self._items[group_id] = []
        self._current_index[group_id] = -1

    def sort_list(self, group_id: str) -> None:
        group_id = str(group_id)
        self._ensure_group(group_id)
        self._items[group_id].sort(key=lambda x: x.init_value, reverse=True)

    def next_turn(self, group_id: str) -> Optional[InitiativeItem]:
        group_id = str(group_id)
        self._ensure_group(group_id)
        if not self._items[group_id]:
            return None

        if self._current_index[group_id] < 0:
            self._current_index[group_id] = 0
        else:
            self._current_index[group_id] = (self._current_index[group_id] + 1) % len(self._items[group_id])

        return self._items[group_id][self._current_index[group_id]]

    def current_turn(self, group_id: str) -> Optional[InitiativeItem]:
        group_id = str(group_id)
        self._ensure_group(group_id)
        if not self._items[group_id]:
            return None
        index = self._current_index[group_id]
        if index < 0 or index >= len(self._items[group_id]):
            return None
        return self._items[group_id][index]

    def format_list(self, group_id: str) -> str:
        group_id = str(group_id)
        self._ensure_group(group_id)
        if not self._items[group_id]:
            return get_output("initiative.empty")

        lines = []
        for i, item in enumerate(self._items[group_id]):
            prefix = "-> " if i == self._current_index[group_id] else "   "
            lines.append(f"{prefix}{item.name}: {item.init_value}")
        return "\n".join(lines)

    def parse_roll(self, expr: Optional[str], default_name: str) -> Tuple[int, str]:
        """解析 .ri 参数,返回 (先攻值, 名字)。

        表达式部分与 .rd 一致,其后的文字作为独立单位的名字(DM 可为不同怪物分别掷):
          空 / +2 / +5+d4 / d20+3 / 2d6 / 20+5+d4(开头数字=骰面,同 .rd20) / 14(仅数字=固定值)
        """
        expr = (expr or "").strip()
        if not expr:
            return random.randint(1, 20), default_name

        dice = r"\d*d\d+"
        chain = r"(?:[+\-*/](?:" + dice + r"|\d+))"

        def evaluate(dice_expr: str, name: str) -> Optional[Tuple[int, str]]:
            total, _ = parse_dice_expression(dice_expr)
            if total is None:
                return None
            return int(total), name.strip() or default_name

        # 只有修正项(".ri+2 名字" / ".ri+5+d4 名字"):1d20 + 修正
        m = re.match(r"^((?:[+\-](?:" + dice + r"|\d+))+)\s*(.*)$", expr, re.IGNORECASE | re.DOTALL)
        if m and (r := evaluate("1d20" + m.group(1), m.group(2))):
            return r

        # 骰式开头(".ri d20+3 名字" / ".ri 2d6 头目")
        m = re.match(r"^(" + dice + r")(" + chain + r"*)\s*(.*)$", expr, re.IGNORECASE | re.DOTALL)
        if m and (r := evaluate(m.group(1) + m.group(2), m.group(3))):
            return r

        # 数字后带修正(".ri20+5+d4 名字"):数字当骰面,和 .rd20 一致
        m = re.match(r"^(\d+)(" + chain + r"+)\s*(.*)$", expr, re.IGNORECASE | re.DOTALL)
        if m and (r := evaluate("1d" + m.group(1) + m.group(2), m.group(3))):
            return r

        # 纯数字 = 固定先攻值(".ri 14 名字")
        m = re.match(r"^(\d+)\s*(.*)$", expr, re.DOTALL)
        if m:
            return int(m.group(1)), m.group(2).strip() or default_name

        # 只写了名字(".ri 枯刃藤怪"):d20 先攻
        return random.randint(1, 20), expr
