from decimal import Decimal
from io import BytesIO
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from schemas.document import DocumentInput
from schemas.report import ReportCategoryResult, ReportCurrencyResult, ReportResult
from services.exceptions import ServiceError
from services.report_service import ReportService


class ReportImageService:
    _WHITE = "#F4F3EE"
    _MUTED = "#A4A6B3"
    _LIME = "#D3FA75"
    _PURPLE = "#B3A0F5"
    _SCALE = 2

    def __init__(self) -> None:
        self._image = Image.new("RGB", (2160, 3280), "#101216")
        self._draw = ImageDraw.Draw(self._image)
        self._fonts: dict[tuple[int, bool], ImageFont.FreeTypeFont] = {}

    def _font(self, size: int, bold: bool) -> ImageFont.FreeTypeFont:
        key = (size, bold)
        if key not in self._fonts:
            font = ImageFont.truetype(
                str(Path(__file__).parent / "fonts" / "Manrope.ttf"), size * self._SCALE
            )
            font.set_variation_by_axes([700 if bold else 400])
            self._fonts[key] = font
        return self._fonts[key]

    def _text(
        self,
        x: int,
        y: int,
        text: str,
        size: int = 22,
        *,
        width: int = 900,
        bold: bool = False,
        color: str = _WHITE,
        truncate: bool = True,
    ) -> None:
        text = " ".join(text.split())
        font = self._font(size, bold)
        while font.getlength(text) > width * self._SCALE and size > 14:
            size -= 1
            font = self._font(size, bold)
        if not truncate and font.getlength(text) > width * self._SCALE:
            raise ServiceError(
                "Суммы слишком длинные для читаемого PNG. Отчёт показан текстом полностью."
            )
        while text and font.getlength(text) > width * self._SCALE:
            text = text[:-2].rstrip("…") + "…"
        self._draw.text((x * self._SCALE, y * self._SCALE), text, font=font, fill=color)

    def _box(
        self,
        x: int,
        y: int,
        right: int,
        bottom: int,
        *,
        color: str = "#191C22",
        radius: int = 22,
    ) -> None:
        self._draw.rounded_rectangle(
            (x * 2, y * 2, right * 2, bottom * 2),
            radius=radius * 2,
            fill=color,
        )

    @classmethod
    def render(cls, report: ReportResult) -> list[DocumentInput]:
        if len(report.currencies) > 12:
            raise ServiceError(
                "Для изображения поддерживается до 12 валют. Текстовый отчёт доступен полностью."
            )
        sections = report.currencies or [ReportCurrencyResult(currency_code="—")]
        try:
            return [
                DocumentInput(
                    name=f"report-{report.date_from}-{report.date_to}-{index + 1}.png",
                    data=cls()._render(report, section),
                )
                for index, section in enumerate(sections)
            ]
        except (OSError, ValueError) as error:
            raise ServiceError(
                "Не удалось построить PNG. Проверьте Pillow и комплектный шрифт."
            ) from error

    def _render(self, report: ReportResult, section: ReportCurrencyResult) -> bytes:
        amount = ReportService.format_amount
        balance = section.balance
        difference = section.difference
        self._text(48, 40, "budgetflow", 32, bold=True)
        self._text(770, 49, section.currency_code, 22, width=262, color=self._LIME)
        self._text(48, 108, "Твой отчёт", 62, bold=True)
        self._text(
            50,
            188,
            f"{report.date_from:%d.%m.%Y} — {report.date_to:%d.%m.%Y}",
            color=self._MUTED,
        )
        self._box(48, 236, 1032, 426)
        self._text(78, 255, "НА СЧЕТАХ СЕЙЧАС", 18, color=self._MUTED)
        self._text(74, 286, amount(balance), 80, width=920, bold=True, truncate=False)
        self._text(
            80,
            389,
            f"{report.balance_at:%d.%m.%Y %H:%M %z} · {section.currency_code}",
            18,
            color=self._MUTED,
        )
        for x, title, value, color in (
            (48, "Доходы", section.income, self._LIME),
            (552, "Расходы", section.expense, self._PURPLE),
        ):
            self._box(x, 448, x + 480, 578, color=color)
            self._text(x + 28, 466, title, 22, color="#17191B")
            self._text(
                x + 28,
                504,
                amount(value),
                44,
                width=424,
                bold=True,
                color="#17191B",
                truncate=False,
            )
        self._box(48, 598, 1032, 644, color="#242D1C", radius=12)
        self._text(70, 607, "Доходы − расходы", 20, width=330, color=self._LIME)
        self._text(
            436,
            604,
            amount(difference),
            24,
            width=340,
            bold=True,
            color=self._LIME,
            truncate=False,
        )
        ratio = (
            f"{difference * 100 / section.income:.1f}% дохода"
            if section.income
            else "Нет доходов"
        )
        self._text(820, 610, ratio, 18, width=190, color=self._LIME, truncate=False)
        self._box(48, 666, 1032, 1070)
        self._text(78, 690, "Куда ушли деньги", 32, bold=True)
        self._text(
            78,
            738,
            f"Расходы по категориям · операций всего: {section.count}",
            18,
            color=self._MUTED,
        )
        categories = section.categories[:5]
        if len(section.categories) > 5:
            categories = [
                *categories,
                ReportCategoryResult(
                    name=f"Остальные категории ({len(section.categories) - 5})",
                    amount=sum(
                        (item.amount for item in section.categories[5:]),
                        Decimal("0.00"),
                    ),
                ),
            ]
        maximum = max((item.amount for item in categories), default=Decimal(1))
        colors = (self._LIME, self._PURPLE, "#90BAF1", "#F3B19C", "#A8ADB9", "#7CAFA5")
        for index, item in enumerate(categories):
            y = 786 + index * 44
            self._text(78, y, item.name, 21, width=228)
            self._box(322, y + 6, 682, y + 25, color="#292D36", radius=4)
            length = int(item.amount * 360 / maximum) if maximum else 0
            if length:
                self._box(
                    322, y + 6, 322 + length, y + 25, color=colors[index], radius=4
                )
            self._text(704, y, amount(item.amount), 21, width=202, truncate=False)
            self._text(
                928,
                y + 2,
                f"{item.amount * 100 / section.expense:.1f}%",
                18,
                width=76,
                color=self._MUTED,
            )
        if not categories:
            self._text(78, 820, "За этот период расходов нет", 24, color=self._MUTED)
        self._box(48, 1092, 610, 1456)
        self._text(78, 1116, "Динамика расходов", 24, bold=True, width=500)
        self._text(78, 1154, f"Суммы в {section.currency_code}", 16, color=self._MUTED)
        maximum = max((item.amount for item in section.periods), default=Decimal(0))
        self._draw.line((156, 2736, 1160, 2736), fill="#404551", width=2)
        if not maximum:
            self._text(78, 1235, "Расходов нет", 22, color=self._MUTED)
        for index, period in enumerate(section.periods):
            count = len(section.periods)
            x = 80 + index * (500 // count)
            bar_width = min(60, 500 // count - 14)
            height = int(period.amount * 158 / maximum) if maximum else 0
            if height:
                self._box(
                    x, 1368 - height, x + bar_width, 1368, color=self._PURPLE, radius=4
                )
                self._text(
                    x,
                    1338 - height,
                    amount(period.amount),
                    18,
                    width=500 // count - 4,
                    truncate=False,
                )
            self._text(
                x,
                1382,
                f"{period.date_from:%d.%m}",
                16,
                width=bar_width + 12,
                color=self._MUTED,
            )
            self._text(
                x,
                1406,
                f"{period.date_to:%d.%m}",
                16,
                width=bar_width + 12,
                color=self._MUTED,
            )
        self._box(634, 1092, 1032, 1456)
        self._text(664, 1116, "Твои счета", 24, bold=True)
        self._text(664, 1154, "Включая неактивные", 16, color=self._MUTED)
        accounts: list[tuple[str, Decimal]] = [
            (item.name + (" [неактивен]" if not item.is_active else ""), item.balance)
            for item in section.accounts[:3]
        ]
        if len(section.accounts) > 3:
            accounts.append(
                (
                    f"Другие счета ({len(section.accounts) - 3})",
                    sum(
                        (item.balance for item in section.accounts[3:]), Decimal("0.00")
                    ),
                )
            )
        for index, (name, value) in enumerate(accounts):
            y = 1190 + index * 62
            self._text(664, y, name, 18, width=338, color=self._MUTED)
            self._text(
                664, y + 24, amount(value), 24, width=338, bold=True, truncate=False
            )
        if not accounts:
            self._text(664, 1220, "Счетов нет", 22, color=self._MUTED)
        self._text(
            48,
            1480,
            "Остатки — на текущий момент, обороты — за выбранный период.",
            17,
            color=self._MUTED,
        )
        self._text(
            48,
            1510,
            "Лимиты и карточки долгов не прибавляются к остаткам.",
            17,
            color=self._MUTED,
        )
        if section.unassigned_count:
            self._text(
                48,
                1540,
                f"Без счёта: {section.unassigned_count} операций. Включены только в обороты.",
                17,
                color=self._MUTED,
            )
        self._text(48, 1590, "BUDGETFLOW / ЛИЧНЫЕ ФИНАНСЫ", 16, color=self._MUTED)
        output = BytesIO()
        self._image.resize((1080, 1640), Image.Resampling.LANCZOS).save(
            output, format="PNG"
        )
        return output.getvalue()
