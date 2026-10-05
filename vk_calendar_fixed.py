import json
import datetime
import calendar
import random
from typing import List, Dict, Any, Optional, Tuple

import vk_api
from vk_api.keyboard import VkKeyboard, VkKeyboardColor
from vk_api.longpoll import VkLongPoll, VkEventType

# =====================================================================
#  Конфигурация
# =====================================================================
VK_TOKEN = "vk1.a.beF9TROZWJ7NpukfVBIrBSU1Uid-HY7k7OReboAQ8G1IetNYIVVo0LMzsunxfAbop8Fa5vfS3XsJBKyjOy8TqmXSk-X7_0lfUTo1E2EfXyeKNNHfynGIg1msxPG1-LuEmsepyKISulO4hhItRL0pfVqxv2A4x78bU_3PACt7WkANOTZ3ZjGO7VSaSBSKDEHt8e2vXtZQJC_VBU36a02h6g"
GROUP_ID = 241165606

CALENDAR_FILE = "storage.json"
HOLIDAYS_FILE = "holidays.json"
STATE_FILE = "bot_state.json"

WEEKDAY_SHORT = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"]

# Unicode figure space — имеет ту же ширину, что и цифра,
# поэтому пустые ячейки не съезжают в пропорциональном шрифте VK.
FIG_SPACE = "\u2007"
# Combining dot above (\u0307) — нулевая ширина (zero advance width),
# не влияет на выравнивание. Ставится после figure space, чтобы
# визуально отметить день с событием точкой сверху.
DOT_ABOVE = "\u0307"
MONTH_NAMES_RU = [
    "", "Январь", "Февраль", "Март", "Апрель", "Май", "Июнь",
    "Июль", "Август", "Сентябрь", "Октябрь", "Ноябрь", "Декабрь",
]


# =====================================================================
#  Утилиты для работы с JSON
# =====================================================================
def load_json(path: str, default: Any) -> Any:
    """Загружает JSON-файл, при ошибке возвращает значение по умолчанию."""
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return default


def save_json(path: str, data: Any) -> None:
    """Сохраняет данные в JSON-файл."""
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except IOError as exc:
        print(f"Ошибка записи файла {path}: {exc}")


# =====================================================================
#  Утилиты для работы с датами
# =====================================================================
def parse_user_date(text: str) -> Optional[str]:
    """Парсит дату из пользовательского ввода.

    Поддерживаемые форматы:
      ДД.ММ.ГГГГ  -> 2025-06-15
      ДД.ММ       -> 2025-06-15 (текущий/следующий год)
      ГГГГ-ММ-ДД  -> 2025-06-15 (обратная совместимость)

    Возвращает строку в формате ГГГГ-ММ-ДД или None при ошибке.
    """
    text = text.strip()

    # Формат ДД.ММ.ГГГГ
    parts = text.split(".")
    if len(parts) == 3:
        try:
            d, m, y = int(parts[0]), int(parts[1]), int(parts[2])
            result = datetime.date(y, m, d)
            return result.isoformat()
        except ValueError:
            return None

    # Формат ДД.ММ (без года)
    if len(parts) == 2:
        try:
            d, m = int(parts[0]), int(parts[1])
            today = datetime.date.today()
            y = today.year
            candidate = datetime.date(y, m, d)
            if candidate < today:
                y += 1
            return datetime.date(y, m, d).isoformat()
        except ValueError:
            return None

    # Формат ГГГГ-ММ-ДД (обратная совместимость)
    dash_parts = text.split("-")
    if len(dash_parts) == 3:
        try:
            y, m, d = (int(dash_parts[0]), int(dash_parts[1]),
                       int(dash_parts[2]))
            return datetime.date(y, m, d).isoformat()
        except ValueError:
            return None

    return None


def parse_multiple_dates(text: str) -> Tuple[List[str], List[str]]:
    """Парсит несколько дат из строки, разделённых запятой.

    Возвращает кортеж (список_валидных_дат, список_ошибок).
    """
    valid_dates = []
    errors = []
    parts = [p.strip() for p in text.split(",") if p.strip()]
    for part in parts:
        parsed = parse_user_date(part)
        if parsed:
            valid_dates.append(parsed)
        else:
            errors.append(part)
    return valid_dates, errors


def format_date_ru(date_str: str) -> str:
    """Форматирует дату ГГГГ-ММ-ДД в ДД.ММ.ГГГГ."""
    try:
        d = datetime.date.fromisoformat(date_str)
        return d.strftime("%d.%m.%Y")
    except ValueError:
        return date_str


# =====================================================================
#  Логика календаря
# =====================================================================
class CalendarPlanner:
    """Управление событиями календаря."""

    def __init__(self, calendar_file: str):
        self.calendar_file = calendar_file
        self.events = load_json(calendar_file, {})

    @staticmethod
    def _validate_date(date_str: str) -> bool:
        """Проверяет корректность даты в формате ГГГГ-ММ-ДД."""
        try:
            datetime.datetime.strptime(date_str, "%Y-%m-%d")
            return True
        except ValueError:
            return False

    def add_event(self, date_str: str, title: str,
                  description: str = "") -> str:
        """Добавляет событие на указанную дату."""
        if not self._validate_date(date_str):
            return "❌ Некорректная дата."

        event = {"title": title, "description": description}
        if date_str not in self.events:
            self.events[date_str] = []
        self.events[date_str].append(event)
        save_json(self.calendar_file, self.events)
        return (f"✅ Мероприятие «{title}» добавлено "
                f"на {format_date_ru(date_str)}.")

    def add_event_multi(self, date_list: List[str], title: str,
                        description: str = "") -> str:
        """Добавляет одно событие на несколько дат сразу."""
        added = []
        errors = []
        for date_str in date_list:
            if not self._validate_date(date_str):
                errors.append(date_str)
                continue
            event = {"title": title, "description": description}
            if date_str not in self.events:
                self.events[date_str] = []
            self.events[date_str].append(event)
            added.append(date_str)

        if added:
            save_json(self.calendar_file, self.events)

        if not added:
            return "❌ Ни одна из дат не распознана."

        lines = [f"✅ Мероприятие «{title}» добавлено на:"]
        for d in added:
            lines.append(f"  • {format_date_ru(d)}")
        if errors:
            lines.append("\n⚠️ Не распознаны:")
            for e in errors:
                lines.append(f"  • {e}")
        return "\n".join(lines)

    def update_event_description(self, date_str: str, index: int,
                                 new_description: str) -> Tuple[bool, str]:
        """Обновляет описание события по индексу (начиная с 1)."""
        if not self._validate_date(date_str):
            return False, "❌ Некорректная дата."

        events = self.events.get(date_str)
        if not events or len(events) < index:
            return False, (f"❌ На {format_date_ru(date_str)} нет "
                           f"события под номером {index}.")

        title = events[index - 1].get("title", "[без названия]")
        events[index - 1]["description"] = new_description
        save_json(self.calendar_file, self.events)
        return True, (f"✅ Описание события «{title}» "
                      f"на {format_date_ru(date_str)} обновлено.")

    def get_day_events(self, date_str: str) -> str:
        """Возвращает текстовый список событий на дату."""
        if not self._validate_date(date_str):
            return "❌ Некорректная дата."

        events = self.events.get(date_str, [])
        weekday_idx = datetime.date.fromisoformat(date_str).weekday()
        weekday = WEEKDAY_SHORT[weekday_idx]
        d = datetime.date.fromisoformat(date_str)
        date_label = d.strftime("%d.%m.%Y")

        if not events:
            lines = [
                f"📅 На {date_label} ({weekday}) "
                f"нет запланированных мероприятий."
            ]
        else:
            lines = [f"📆 События на {date_label} ({weekday}):"]
            for i, ev in enumerate(events, 1):
                title = ev.get("title", "Без названия")
                desc = ev.get("description", "")
                line = f"  {i}. {title}"
                if desc:
                    line += f" — {desc}"
                lines.append(line)

        # Добавляем праздники
        holidays = holidays_service.get_holidays_for_date(date_str)
        if holidays:
            lines.append("\n🎉 Праздники:")
            for h in holidays:
                lines.append(f"  • {h}")

        return "\n".join(lines)

    def get_day_events_list(self, date_str: str) -> List[Dict]:
        """Возвращает список событий (для построения кнопок)."""
        return self.events.get(date_str, [])

    def delete_event_safe(self, date_str: str,
                          index: int) -> Tuple[bool, str]:
        """Удаляет событие по индексу (начиная с 1)."""
        if not self._validate_date(date_str):
            return False, "❌ Некорректная дата."

        events = self.events.get(date_str)
        if not events or len(events) < index:
            return False, (f"❌ На {format_date_ru(date_str)} нет "
                           f"события под номером {index}.")

        removed = events.pop(index - 1)
        if not events:
            del self.events[date_str]

        save_json(self.calendar_file, self.events)
        title = removed.get("title", "[без названия]")
        return True, (f"🗑️ Мероприятие «{title}» "
                      f"на {format_date_ru(date_str)} удалено.")

    def get_reminders(self, days_ahead: int = 3) -> str:
        """Возвращает напоминания на ближайшие N дней."""
        today = datetime.date.today()
        lines = [f"⏰ Напоминания на ближайшие {days_ahead} дн.:"]
        found = False

        for d_offset in range(days_ahead):
            check_date = today + datetime.timedelta(days=d_offset)
            date_str = check_date.isoformat()
            events = self.events.get(date_str, [])
            if not events:
                continue

            found = True
            weekday = WEEKDAY_SHORT[check_date.weekday()]
            day_label = f"{check_date.strftime('%d.%m')} ({weekday})"
            lines.append(f"\n📌 {day_label}:")
            for i, ev in enumerate(events, 1):
                title = ev.get("title", "Без названия")
                desc = ev.get("description", "")
                line = f"  {i}. {title}"
                if desc:
                    line += f" — {desc}"
                lines.append(line)

        if not found:
            lines.append("\nВ ближайшие дни нет запланированных событий.")
        return "\n".join(lines)

    def get_month_calendar_grid(self, year: int, month: int) -> str:
        """Возвращает календарь месяца в виде ровной сетки.

        Все ячейки имеют одинаковую ширину: figure space (\u2007,
        ширина = цифра) + 2 цифры. Дни с событиями дополнительно
        отмечаются combining dot above (\u0307) — нулевая ширина,
        не влияет на выравнивание.
        Разделитель между ячейками — 1 обычный пробел.
        """
        cal = calendar.Calendar(firstweekday=0)
        weeks = cal.monthdayscalendar(year, month)
        month_name = MONTH_NAMES_RU[month]
        header = f"📅 {month_name} {year}"

        # Заголовок: пробел + 2 символа = 3 символа на ячейку
        days_header = " ".join(f"{FIG_SPACE}{d}" for d in WEEKDAY_SHORT)

        # Дни с событиями
        events_days = set()
        for date_str, ev_list in self.events.items():
            try:
                y, m, d = map(int, date_str.split("-"))
                if y == year and m == month and ev_list:
                    events_days.add(d)
            except ValueError:
                continue

        lines = [header, "", days_header]

        for week in weeks:
            row_cells = []
            for day in week:
                if day == 0:
                    # Пустая ячейка: 3 figure space (ширина = 3 цифры)
                    row_cells.append(FIG_SPACE * 3)
                elif day in events_days:
                    # День с событием: figure space + combining dot above
                    # (нулевая ширина) + 2 цифры = ширина 3 цифр
                    row_cells.append(f"{FIG_SPACE}{DOT_ABOVE}{day:02d}")
                else:
                    # Обычный день: figure space + 2 цифры = 3 символа
                    row_cells.append(f"{FIG_SPACE}{day:02d}")
            lines.append(" ".join(row_cells))

        lines.append("")
        lines.append(f"{FIG_SPACE}{DOT_ABOVE} — день с событием")

        # Список событий под сеткой
        month_events = self._get_month_events_list(year, month)
        if month_events:
            lines.append("")
            lines.append(month_events)
        else:
            lines.append("")
            lines.append("В этом месяце нет запланированных мероприятий.")

        return "\n".join(lines)

    def _get_month_events_list(self, year: int, month: int) -> str:
        """Возвращает текстовый список событий месяца."""
        result_lines = ["📋 События месяца:"]
        found = False
        for date_str in sorted(self.events.keys()):
            try:
                y, m, d = map(int, date_str.split("-"))
            except ValueError:
                continue
            if y == year and m == month:
                found = True
                events = self.events[date_str]
                weekday = WEEKDAY_SHORT[
                    datetime.date(year, month, d).weekday()
                ]
                result_lines.append(f"\n{d:02d}.{m:02d} ({weekday}):")
                for i, ev in enumerate(events, 1):
                    title = ev.get("title", "Без названия")
                    desc = ev.get("description", "")
                    line = f"  {i}. {title}"
                    if desc:
                        line += f" — {desc}"
                    result_lines.append(line)
        return "\n".join(result_lines) if found else ""


# =====================================================================
#  Праздники
# =====================================================================
class HolidayService:
    """Загрузка и поиск праздников."""

    def __init__(self, holidays_file: str):
        self.holidays = load_json(holidays_file, [])

    def get_holidays_for_date(self, date_str: str) -> List[str]:
        """Возвращает до 4 праздников для конкретной даты."""
        try:
            y, m, d = map(int, date_str.split("-"))
            mmdd = f"{m:02d}-{d:02d}"
        except ValueError:
            return []
        matched = [h["name"] for h in self.holidays
                   if h.get("date") == mmdd]
        return matched[:4]

    def get_today_holidays(self) -> List[str]:
        """Возвращает до 4 праздников на сегодня."""
        today = datetime.date.today()
        mmdd = f"{today.month:02d}-{today.day:02d}"
        matched = [h["name"] for h in self.holidays
                   if h.get("date") == mmdd]
        return matched[:4]


# =====================================================================
#  Менеджер состояний
# =====================================================================
class BotStateManager:
    """Управляет многошаговыми сценариями диалога."""

    def __init__(self, state_file: str):
        self.state_file = state_file
        self.states = load_json(state_file, {})

    def set_state(self, user_id: int, state: Dict) -> None:
        self.states[str(user_id)] = state
        save_json(self.state_file, self.states)

    def get_state(self, user_id: int) -> Optional[Dict]:
        return self.states.get(str(user_id))

    def clear(self, user_id: int) -> None:
        self.states.pop(str(user_id), None)
        save_json(self.state_file, self.states)


# =====================================================================
#  Построитель клавиатур
# =====================================================================
class KeyboardBuilder:
    """Строит VK-клавиатуры для разных экранов."""

    @staticmethod
    def main_menu() -> str:
        kb = VkKeyboard(one_time=False)
        kb.add_button("🗓 Добавить", color=VkKeyboardColor.PRIMARY)
        kb.add_button("✏️ Изменить", color=VkKeyboardColor.SECONDARY)
        kb.add_line()
        kb.add_button("📆 Сегодня", color=VkKeyboardColor.SECONDARY)
        kb.add_button("📅 Календарь", color=VkKeyboardColor.SECONDARY)
        kb.add_line()
        kb.add_button("⏰ Напоминание", color=VkKeyboardColor.PRIMARY)
        kb.add_button("🎉 Праздники", color=VkKeyboardColor.POSITIVE)
        kb.add_line()
        kb.add_button("🗑 Удалить", color=VkKeyboardColor.NEGATIVE)
        return kb.get_keyboard()

    @staticmethod
    def date_picker() -> str:
        """Клавиатура выбора даты."""
        kb = VkKeyboard(one_time=True)
        today = datetime.date.today()
        tomorrow = today + datetime.timedelta(days=1)
        after = today + datetime.timedelta(days=2)

        kb.add_button(
            f"📅 {today.strftime('%d.%m')} (сегодня)",
            color=VkKeyboardColor.PRIMARY,
        )
        kb.add_line()
        kb.add_button(
            f"📅 {tomorrow.strftime('%d.%m')} (завтра)",
            color=VkKeyboardColor.SECONDARY,
        )
        kb.add_line()
        kb.add_button(
            f"📅 {after.strftime('%d.%m')} (послезавтра)",
            color=VkKeyboardColor.SECONDARY,
        )
        kb.add_line()
        kb.add_button("⌨️ Ввести дату вручную",
                      color=VkKeyboardColor.SECONDARY)
        kb.add_line()
        kb.add_button("📅📅 Несколько дат",
                      color=VkKeyboardColor.SECONDARY)
        kb.add_line()
        kb.add_button("🔙 Главное меню",
                      color=VkKeyboardColor.SECONDARY)
        return kb.get_keyboard()

    @staticmethod
    def skip_and_back() -> str:
        """Кнопки «Пропустить» и «Главное меню»."""
        kb = VkKeyboard(one_time=True)
        kb.add_button("⏭ Без описания", color=VkKeyboardColor.SECONDARY)
        kb.add_button("🔙 Главное меню", color=VkKeyboardColor.SECONDARY)
        return kb.get_keyboard()

    @staticmethod
    def back_only() -> str:
        """Только кнопка возврата."""
        kb = VkKeyboard(one_time=True)
        kb.add_button("🔙 Главное меню",
                      color=VkKeyboardColor.SECONDARY)
        return kb.get_keyboard()

    @staticmethod
    def confirmation_menu() -> str:
        kb = VkKeyboard(one_time=True)
        kb.add_button("✅ Да, удалить", color=VkKeyboardColor.NEGATIVE)
        kb.add_button("❌ Отмена", color=VkKeyboardColor.SECONDARY)
        kb.add_line()
        kb.add_button("🔙 Главное меню",
                      color=VkKeyboardColor.SECONDARY)
        return kb.get_keyboard()

    @staticmethod
    def edit_clear_and_back() -> str:
        """Кнопки для ввода нового описания."""
        kb = VkKeyboard(one_time=True)
        kb.add_button("🗑 Очистить описание",
                      color=VkKeyboardColor.NEGATIVE)
        kb.add_button("🔙 Главное меню",
                      color=VkKeyboardColor.SECONDARY)
        return kb.get_keyboard()

    @staticmethod
    def calendar_nav() -> str:
        """Навигация по месяцам + главное меню."""
        kb = VkKeyboard(one_time=False)
        kb.add_button("◀️ Предыдущий",
                      color=VkKeyboardColor.SECONDARY)
        kb.add_button("Следующий ▶️",
                      color=VkKeyboardColor.SECONDARY)
        kb.add_line()
        kb.add_button("🔙 Главное меню",
                      color=VkKeyboardColor.SECONDARY)
        return kb.get_keyboard()

    @staticmethod
    def no_keyboard() -> str:
        """Пустая клавиатура (для свободного ввода текста)."""
        return VkKeyboard().get_empty_keyboard()


# =====================================================================
#  Инициализация
# =====================================================================
planner = CalendarPlanner(CALENDAR_FILE)
holidays_service = HolidayService(HOLIDAYS_FILE)
state_manager = BotStateManager(STATE_FILE)

MENU_MSG = (
    "📋 Календарь-бот\n\n"
    "Выберите действие на панели кнопок:"
)


# =====================================================================
#  Обработка сообщений
# =====================================================================
def handle_message(text: str, user_id: int) -> Tuple[str, str]:
    text = text.strip()
    state = state_manager.get_state(user_id)

    # --- Кнопка «Главное меню» всегда сбрасывает состояние ---
    if text == "🔙 Главное меню":
        state_manager.clear(user_id)
        return MENU_MSG, KeyboardBuilder.main_menu()

    # --- Если есть активное состояние ---
    if state:
        return _handle_state(text, user_id, state)

    # --- Нет состояния — главное меню ---
    return _handle_main(text, user_id)


def _handle_main(text: str, user_id: int) -> Tuple[str, str]:
    """Обработка нажатий из главного меню."""

    if text == "" or text == "Начать" or text == "start":
        return MENU_MSG, KeyboardBuilder.main_menu()

    if text == "🗓 Добавить":
        state_manager.set_state(user_id,
                                {"action": "add", "step": "date"})
        return (
            "🗓 Добавление мероприятия\n\n"
            "Выберите дату или введите вручную (ДД.ММ.ГГГГ):",
            KeyboardBuilder.date_picker(),
        )

    if text == "✏️ Изменить":
        state_manager.set_state(user_id,
                                {"action": "edit", "step": "date"})
        return (
            "✏️ Изменение описания мероприятия\n\n"
            "Выберите дату события:",
            KeyboardBuilder.date_picker(),
        )

    if text == "📆 Сегодня":
        today_str = datetime.date.today().isoformat()
        return (planner.get_day_events(today_str),
                KeyboardBuilder.back_only())

    if text == "📅 Календарь":
        today = datetime.date.today()
        state_manager.set_state(user_id, {
            "action": "calendar",
            "year": today.year,
            "month": today.month,
        })
        grid = planner.get_month_calendar_grid(today.year, today.month)
        return grid, KeyboardBuilder.calendar_nav()

    if text == "⏰ Напоминание":
        return planner.get_reminders(3), KeyboardBuilder.back_only()

    if text == "🗑 Удалить":
        state_manager.set_state(
            user_id, {"action": "delete", "step": "date"}
        )
        return (
            "🗑 Удаление мероприятия\n\n"
            "Выберите дату события для удаления:",
            KeyboardBuilder.date_picker(),
        )

    if text == "🎉 Праздники":
        holidays = holidays_service.get_today_holidays()
        if not holidays:
            msg = "Сегодня нет отмеченных праздников."
        else:
            lines = ["🎉 Сегодня праздники:"]
            for h in holidays:
                lines.append(f"  • {h}")
            msg = "\n".join(lines)
        return msg, KeyboardBuilder.back_only()

    return MENU_MSG, KeyboardBuilder.main_menu()


def _handle_state(text: str, user_id: int,
                  state: Dict) -> Tuple[str, str]:
    """Маршрутизация многошаговых сценариев."""
    action = state.get("action")

    if action == "add":
        return _handle_add(text, user_id, state)
    elif action == "delete":
        return _handle_delete(text, user_id, state)
    elif action == "edit":
        return _handle_edit(text, user_id, state)
    elif action == "calendar":
        return _handle_calendar(text, user_id, state)
    elif action == "manual_date":
        return _handle_manual_date(text, user_id, state)
    elif action == "multi_date":
        return _handle_multi_date(text, user_id, state)

    state_manager.clear(user_id)
    return MENU_MSG, KeyboardBuilder.main_menu()


def _resolve_date_button(text: str) -> Optional[str]:
    """Извлекает дату из текста кнопки вида '📅 15.06 (сегодня)'."""
    try:
        raw = text.replace("📅", "").strip()
        date_part = raw.split()[0]
        d, m = map(int, date_part.split("."))
        y = datetime.date.today().year
        today = datetime.date.today()
        if m < today.month or (m == today.month and d < today.day):
            y += 1
        return f"{y}-{m:02d}-{d:02d}"
    except (ValueError, IndexError):
        return None


def _handle_add(text: str, user_id: int,
                state: Dict) -> Tuple[str, str]:
    """Сценарий добавления события."""
    step = state.get("step")

    if step == "date":
        if text == "⌨️ Ввести дату вручную":
            state["step"] = "manual_date"
            state["return_action"] = "add"
            state_manager.set_state(user_id, state)
            return (
                "Введите дату в формате ДД.ММ.ГГГГ:\n"
                "Пример: 15.06.2025\n\n"
                "Можно без года: 15.06",
                KeyboardBuilder.back_only(),
            )

        if text == "📅📅 Несколько дат":
            state["action"] = "multi_date"
            state["step"] = "enter_dates"
            state["return_action"] = "add"
            state_manager.set_state(user_id, state)
            return (
                "📅📅 Ввод нескольких дат\n\n"
                "Введите даты через запятую.\n"
                "Формат: ДД.ММ.ГГГГ\n\n"
                "Пример: 15.06.2025, 20.06.2025, 01.07.2025",
                KeyboardBuilder.back_only(),
            )

        date_str = _resolve_date_button(text)
        if not date_str:
            date_str = parse_user_date(text)
            if not date_str:
                return (
                    "⚠️ Не удалось распознать дату.\n"
                    "Выберите кнопку или введите ДД.ММ.ГГГГ.",
                    KeyboardBuilder.date_picker(),
                )

        state["step"] = "title"
        state["date"] = date_str
        state_manager.set_state(user_id, state)
        return (
            f"✅ Дата: {format_date_ru(date_str)}\n\n"
            "Введите название мероприятия:",
            KeyboardBuilder.back_only(),
        )

    if step == "title":
        date_str = state.get("date", "")
        state["step"] = "description"
        state["title"] = text
        state_manager.set_state(user_id, state)
        return (
            f"✅ Название: {text}\n\n"
            "Введите описание (или нажмите «Без описания»):",
            KeyboardBuilder.skip_and_back(),
        )

    if step == "description":
        date_str = state.get("date", "")
        title = state.get("title", "")
        if text == "⏭ Без описания":
            description = ""
        else:
            description = text
        msg = planner.add_event(date_str, title, description)
        state_manager.clear(user_id)
        return msg, KeyboardBuilder.main_menu()

    state_manager.clear(user_id)
    return MENU_MSG, KeyboardBuilder.main_menu()


def _handle_multi_date(text: str, user_id: int,
                       state: Dict) -> Tuple[str, str]:
    """Сценарий ввода нескольких дат."""
    step = state.get("step", "enter_dates")

    if step == "enter_dates":
        valid_dates, errors = parse_multiple_dates(text)
        if not valid_dates:
            return (
                "⚠️ Ни одна дата не распознана.\n"
                "Формат: ДД.ММ.ГГГГ через запятую\n"
                "Пример: 15.06.2025, 20.06.2025",
                KeyboardBuilder.back_only(),
            )

        state["step"] = "title"
        state["dates"] = valid_dates
        date_list_ru = ", ".join(format_date_ru(d) for d in valid_dates)
        state_manager.set_state(user_id, state)

        error_msg = ""
        if errors:
            error_msg = f"\n\n⚠️ Не распознаны: {', '.join(errors)}"

        return (
            f"✅ Даты: {date_list_ru}\n{error_msg}\n\n"
            "Введите название мероприятия:",
            KeyboardBuilder.back_only(),
        )

    if step == "title":
        dates = state.get("dates", [])
        state["step"] = "description"
        state["title"] = text
        state_manager.set_state(user_id, state)
        return (
            f"✅ Название: {text}\n\n"
            "Введите описание (или нажмите «Без описания»):",
            KeyboardBuilder.skip_and_back(),
        )

    if step == "description":
        dates = state.get("dates", [])
        title = state.get("title", "")
        if text == "⏭ Без описания":
            description = ""
        else:
            description = text
        msg = planner.add_event_multi(dates, title, description)
        state_manager.clear(user_id)
        return msg, KeyboardBuilder.main_menu()

    state_manager.clear(user_id)
    return MENU_MSG, KeyboardBuilder.main_menu()


def _handle_delete(text: str, user_id: int,
                   state: Dict) -> Tuple[str, str]:
    """Сценарий удаления события."""
    step = state.get("step")

    if step == "date":
        if text == "⌨️ Ввести дату вручную":
            state["step"] = "manual_date"
            state["return_action"] = "delete"
            state_manager.set_state(user_id, state)
            return (
                "Введите дату в формате ДД.ММ.ГГГГ:\n"
                "Пример: 15.06.2025",
                KeyboardBuilder.back_only(),
            )

        if text == "📅📅 Несколько дат":
            return (
                "Удаление работает только с одной датой.\n"
                "Выберите дату:",
                KeyboardBuilder.date_picker(),
            )

        date_str = _resolve_date_button(text)
        if not date_str:
            date_str = parse_user_date(text)
            if not date_str:
                return (
                    "⚠️ Не удалось распознать дату.\n"
                    "Выберите кнопку или введите ДД.ММ.ГГГГ.",
                    KeyboardBuilder.date_picker(),
                )

        events = planner.get_day_events_list(date_str)
        if not events:
            state_manager.clear(user_id)
            return (
                f"❌ На {format_date_ru(date_str)} "
                f"нет событий для удаления.",
                KeyboardBuilder.back_only(),
            )

        kb = VkKeyboard(one_time=True)
        for i, ev in enumerate(events, 1):
            title = ev.get("title", "Без названия")
            label = f"🗑 {i}. {title[:30]}"
            kb.add_button(label, color=VkKeyboardColor.NEGATIVE)
            if i % 2 == 0:
                kb.add_line()
        kb.add_line()
        kb.add_button("🔙 Главное меню",
                      color=VkKeyboardColor.SECONDARY)

        state["step"] = "choose_event"
        state["date"] = date_str
        state_manager.set_state(user_id, state)

        lines = [
            f"🗑 Удаление на {format_date_ru(date_str)}",
            "Выберите событие:",
        ]
        for i, ev in enumerate(events, 1):
            title = ev.get("title", "Без названия")
            desc = ev.get("description", "")
            line = f"  {i}. {title}"
            if desc:
                line += f" — {desc}"
            lines.append(line)
        return "\n".join(lines), kb.get_keyboard()

    if step == "choose_event":
        date_str = state.get("date", "")
        index = None
        if text.startswith("🗑"):
            try:
                num_part = text.replace("🗑", "").strip().split(".")[0]
                index = int(num_part)
            except (ValueError, IndexError):
                pass
        if index is None:
            try:
                index = int(text)
            except ValueError:
                return (
                    "⚠️ Выберите событие кнопкой ниже.",
                    KeyboardBuilder.back_only(),
                )

        events = planner.get_day_events_list(date_str)
        if not events or len(events) < index:
            return (
                f"❌ События №{index} на "
                f"{format_date_ru(date_str)} не существует.",
                KeyboardBuilder.back_only(),
            )

        title = events[index - 1].get("title", "[без названия]")
        state["step"] = "confirm"
        state["index"] = index
        state_manager.set_state(user_id, state)

        return (
            f"⚠️ Подтвердите удаление:\n"
            f"«{title}» ({format_date_ru(date_str)}, №{index})",
            KeyboardBuilder.confirmation_menu(),
        )

    if step == "confirm":
        resp = text.lower().strip()
        date_str = state.get("date", "")
        index = state.get("index", 0)

        if resp in ("да", "подтверждаю", "ок", "✅ да, удалить"):
            success, msg = planner.delete_event_safe(date_str, index)
            state_manager.clear(user_id)
            return msg, KeyboardBuilder.main_menu()
        else:
            state_manager.clear(user_id)
            return "Удаление отменено.", KeyboardBuilder.main_menu()

    state_manager.clear(user_id)
    return MENU_MSG, KeyboardBuilder.main_menu()


def _handle_edit(text: str, user_id: int,
                 state: Dict) -> Tuple[str, str]:
    """Сценарий изменения описания события."""
    step = state.get("step")

    if step == "date":
        if text == "⌨️ Ввести дату вручную":
            state["step"] = "manual_date"
            state["return_action"] = "edit"
            state_manager.set_state(user_id, state)
            return (
                "Введите дату в формате ДД.ММ.ГГГГ:\n"
                "Пример: 15.06.2025",
                KeyboardBuilder.back_only(),
            )

        if text == "📅📅 Несколько дат":
            return (
                "Изменение работает только с одной датой.\n"
                "Выберите дату:",
                KeyboardBuilder.date_picker(),
            )

        date_str = _resolve_date_button(text)
        if not date_str:
            date_str = parse_user_date(text)
            if not date_str:
                return (
                    "⚠️ Не удалось распознать дату.\n"
                    "Выберите кнопку или введите ДД.ММ.ГГГГ.",
                    KeyboardBuilder.date_picker(),
                )

        events = planner.get_day_events_list(date_str)
        if not events:
            state_manager.clear(user_id)
            return (
                f"❌ На {format_date_ru(date_str)} "
                f"нет событий для изменения.",
                KeyboardBuilder.back_only(),
            )

        kb = VkKeyboard(one_time=True)
        for i, ev in enumerate(events, 1):
            title = ev.get("title", "Без названия")
            label = f"✏️ {i}. {title[:30]}"
            kb.add_button(label, color=VkKeyboardColor.SECONDARY)
            if i % 2 == 0:
                kb.add_line()
        kb.add_line()
        kb.add_button("🔙 Главное меню",
                      color=VkKeyboardColor.SECONDARY)

        state["step"] = "choose_event"
        state["date"] = date_str
        state_manager.set_state(user_id, state)

        lines = [
            f"✏️ Изменение на {format_date_ru(date_str)}",
            "Выберите событие:",
        ]
        for i, ev in enumerate(events, 1):
            title = ev.get("title", "Без названия")
            desc = ev.get("description", "")
            line = f"  {i}. {title}"
            if desc:
                line += f" — {desc}"
            lines.append(line)
        return "\n".join(lines), kb.get_keyboard()

    if step == "choose_event":
        date_str = state.get("date", "")
        index = None
        if text.startswith("✏️"):
            try:
                num_part = text.replace("✏️", "").strip().split(".")[0]
                index = int(num_part)
            except (ValueError, IndexError):
                pass
        if index is None:
            try:
                index = int(text)
            except ValueError:
                return (
                    "⚠️ Выберите событие кнопкой ниже.",
                    KeyboardBuilder.back_only(),
                )

        events = planner.get_day_events_list(date_str)
        if not events or len(events) < index:
            return (
                f"❌ События №{index} на "
                f"{format_date_ru(date_str)} не существует.",
                KeyboardBuilder.back_only(),
            )

        title = events[index - 1].get("title", "[без названия]")
        old_desc = events[index - 1].get("description", "")

        state["step"] = "new_description"
        state["index"] = index
        state_manager.set_state(user_id, state)

        desc_info = ""
        if old_desc:
            desc_info = f"\n📋 Текущее описание:\n{old_desc}"
        else:
            desc_info = "\n📋 Описание не задано."

        return (
            f"✏️ Изменение описания\n"
            f"Событие: «{title}» "
            f"({format_date_ru(date_str)}, №{index})"
            f"{desc_info}\n\n"
            "Введите новое описание:\n"
            "(кнопка «🗑 Очистить описание» — удалить)",
            KeyboardBuilder.edit_clear_and_back(),
        )

    if step == "new_description":
        date_str = state.get("date", "")
        index = state.get("index", 0)

        if text == "🗑 Очистить описание":
            new_desc = ""
        else:
            new_desc = text

        success, msg = planner.update_event_description(
            date_str, index, new_desc
        )
        state_manager.clear(user_id)
        return msg, KeyboardBuilder.main_menu()

    state_manager.clear(user_id)
    return MENU_MSG, KeyboardBuilder.main_menu()


def _handle_calendar(text: str, user_id: int,
                     state: Dict) -> Tuple[str, str]:
    """Навигация по месяцам в календаре."""
    year = state.get("year", datetime.date.today().year)
    month = state.get("month", datetime.date.today().month)

    if text == "◀️ Предыдущий":
        month -= 1
        if month < 1:
            month = 12
            year -= 1
    elif text == "Следующий ▶️":
        month += 1
        if month > 12:
            month = 1
            year += 1
    else:
        return (
            planner.get_month_calendar_grid(year, month),
            KeyboardBuilder.calendar_nav(),
        )

    state["year"] = year
    state["month"] = month
    state_manager.set_state(user_id, state)
    return (
        planner.get_month_calendar_grid(year, month),
        KeyboardBuilder.calendar_nav(),
    )


def _handle_manual_date(text: str, user_id: int,
                        state: Dict) -> Tuple[str, str]:
    """Обработка ручного ввода даты."""
    date_str = parse_user_date(text)
    if not date_str:
        return (
            "⚠️ Некорректный формат.\n"
            "Введите дату как ДД.ММ.ГГГГ:\n"
            "Пример: 15.06.2025",
            KeyboardBuilder.back_only(),
        )

    return_action = state.get("return_action", "add")

    if return_action == "add":
        state["action"] = "add"
        state["step"] = "title"
        state["date"] = date_str
        state.pop("return_action", None)
        state_manager.set_state(user_id, state)
        return (
            f"✅ Дата: {format_date_ru(date_str)}\n\n"
            "Введите название мероприятия:",
            KeyboardBuilder.back_only(),
        )

    if return_action == "delete":
        state["action"] = "delete"
        state["step"] = "date"
        state.pop("return_action", None)
        state_manager.set_state(user_id, state)
        return _handle_delete(date_str, user_id, state)

    if return_action == "edit":
        state["action"] = "edit"
        state["step"] = "date"
        state.pop("return_action", None)
        state_manager.set_state(user_id, state)
        return _handle_edit(date_str, user_id, state)

    state_manager.clear(user_id)
    return MENU_MSG, KeyboardBuilder.main_menu()


# =====================================================================
#  Запуск бота
# =====================================================================
def run_bot():
    """Запуск longpoll-сервера бота."""
    vk_session = vk_api.VkApi(token=VK_TOKEN)
    longpoll = VkLongPoll(vk_session)
    vk = vk_session.get_api()

    print("Бот запущен. Ожидание сообщений...")

    for event in longpoll.listen():
        if event.type == VkEventType.MESSAGE_NEW and event.to_me:
            user_id = event.user_id
            text = event.text
            if not text:
                continue

            response, keyboard = handle_message(text, user_id)

            try:
                vk.messages.send(
                    user_id=user_id,
                    message=response,
                    keyboard=keyboard,
                    random_id=random.randint(0, 2**31 - 1),
                )
            except vk_api.exceptions.ApiError as exc:
                print(f"Ошибка отправки сообщения: {exc}")


if __name__ == "__main__":
    run_bot()
