"""
High-Contrast Speed Metaphor Icon Generator for PowerMaster_ASUS (ТЗ-29).
Генерирует крупные, жирные и высококонтрастные иконки трея (64x64 RGBA):
- 🚀 Высокая производительность: Красная ракета с соплом огня.
- 🚗 Сбалансированный режим: Зеленый/голубой легковой автомобиль.
- 🚲 Экономия энергии: Салатовый / желтый велосипед.
- Микро-бейджи источника питания: 🔌 Сеть 220V (вилка), 🍃 Батарея (листик).
- Оранжевый/красный бейдж доступного обновления в левом верхнем углу.

Strict Zero-Stub Policy. Production-ready implementation.
"""

from __future__ import annotations
import logging

from PIL import Image, ImageDraw

logger = logging.getLogger("PowerMaster.IconSpeedMetaphor")

class IconSpeedMetaphorGenerator:
    """
    Генератор высококонтрастных пиктограмм метафоры скорости (64x64).
    Заполняет 95% площади, использует толщину контура >= 3px для идеальной
    видимости при сжатии до 16x16 в трее Windows 11.
    """
    SIZE = (64, 64)

    @classmethod
    def draw_rocket_icon(cls, is_ac: bool, has_update: bool = False) -> Image.Image:
        """🚀 Крупный плотный силуэт красной ракеты (Высокая производительность, прозрачный фон)."""
        img = Image.new("RGBA", cls.SIZE, (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)

        # Мощное огненное сопло снизу (y=43..63)
        flame_outer = [(32, 63), (16, 46), (26, 43), (32, 53), (38, 43), (48, 46)]
        draw.polygon(flame_outer, fill="#FF2200", outline="#990000", width=2)
        flame_inner = [(32, 58), (22, 46), (32, 48), (42, 46)]
        draw.polygon(flame_inner, fill="#FFDD00")

        # Широкие крылья ракеты (x=2..62, y=28..54)
        wing_left = [(2, 54), (19, 28), (19, 46)]
        draw.polygon(wing_left, fill="#C0392B", outline="#4A0E07", width=3)
        wing_right = [(62, 54), (45, 28), (45, 46)]
        draw.polygon(wing_right, fill="#C0392B", outline="#4A0E07", width=3)

        # Массивный фюзеляж ракеты (y=2..47)
        body = [(32, 2), (49, 23), (45, 47), (19, 47), (15, 23)]
        draw.polygon(body, fill="#FF3344", outline="#4A0E07", width=3)

        # Большой круглый иллюминатор
        draw.ellipse([23, 14, 41, 32], fill="#00E5FF", outline="#FFFFFF", width=3)
        draw.ellipse([26, 17, 33, 24], fill="#FFFFFF")

        if has_update:
            cls._draw_update_badge(draw)

        return img

    @classmethod
    def draw_car_icon(cls, is_ac: bool, has_update: bool = False) -> Image.Image:
        """🚗 Крупный плотный профиль синей машины (Сбалансированный режим, прозрачный фон)."""
        img = Image.new("RGBA", cls.SIZE, (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)

        # Массивный кузов (Chunky SUV/Sport-Hatchback, заполняет x=2..62, y=6..48)
        body = [
            (2, 48), (2, 34), (6, 24), (16, 24), (23, 6),
            (43, 6), (53, 24), (62, 32), (62, 48), (54, 48),
            # front wheel arch
            (52, 42), (48, 36), (40, 36), (36, 42), (34, 48),
            # center bottom
            (24, 48),
            # rear wheel arch
            (22, 42), (18, 36), (10, 36), (6, 42), (4, 48)
        ]
        draw.polygon(body, fill="#0984E3", outline="#002D4A", width=3)

        # Крупные контрастные белые окна
        draw.polygon([(17, 22), (24, 9), (31, 9), (31, 22)], fill="#FFFFFF", outline="#002D4A", width=2)
        draw.polygon([(34, 9), (42, 9), (50, 22), (34, 22)], fill="#FFFFFF", outline="#002D4A", width=2)

        # Фары
        draw.rectangle([56, 32, 62, 40], fill="#FFF200")
        draw.rectangle([2, 32, 7, 40], fill="#FF3838")

        # Огромные колеса: диаметр 22px! центры (14, 48) и (44, 48)
        for cx in (14, 44):
            draw.ellipse([cx - 11, 38, cx + 11, 60], fill="#1E272E", outline="#000000", width=3)
            draw.ellipse([cx - 6, 43, cx + 6, 55], fill="#FFFFFF", outline="#747D8C", width=1)
            draw.ellipse([cx - 2, 47, cx + 2, 51], fill="#0984E3")

        if has_update:
            cls._draw_update_badge(draw)

        return img

    @classmethod
    def draw_bicycle_icon(cls, is_ac: bool, has_update: bool = False) -> Image.Image:
        """🚲 Крупный плотный профиль зеленого велосипеда (Экономия энергии, прозрачный фон)."""
        img = Image.new("RGBA", cls.SIZE, (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)

        # Огромные колеса: диаметр 28px! (y=28..58)
        for cx in (14, 48):
            draw.ellipse([cx - 13, 28, cx + 13, 58], outline="#1E272E", width=5)
            draw.ellipse([cx - 9, 32, cx + 9, 54], outline="#00B894", width=2)
            draw.line([(cx, 30), (cx, 56)], fill="#A4B0BE", width=2)
            draw.line([(cx - 12, 43), (cx + 12, 43)], fill="#A4B0BE", width=2)
            draw.ellipse([cx - 3, 40, cx + 3, 46], fill="#2F3542")

        # Сверхжирная изумрудно-зеленая рама: толщина 5px!
        fc = "#00B894"
        draw.line([(14, 43), (31, 43)], fill=fc, width=5)
        draw.line([(14, 43), (23, 20)], fill=fc, width=5)
        draw.line([(31, 43), (23, 20)], fill=fc, width=5)
        draw.line([(31, 43), (43, 16)], fill=fc, width=5)
        draw.line([(23, 20), (43, 16)], fill=fc, width=5)
        draw.line([(43, 16), (48, 43)], fill=fc, width=5)

        # Седло и руль
        draw.line([(23, 20), (21, 13)], fill="#2F3542", width=4)
        draw.polygon([(14, 13), (28, 13), (26, 17), (16, 17)], fill="#2F3542")
        draw.line([(43, 16), (42, 7)], fill="#2F3542", width=4)
        draw.line([(37, 7), (47, 7)], fill="#FFFFFF", width=5)
        draw.ellipse([28, 40, 34, 46], fill="#FFFFFF", outline="#2F3542", width=1)

        if has_update:
            cls._draw_update_badge(draw)

        return img

    @classmethod
    def draw_tile_rocket(cls, is_ac: bool, has_update: bool = False) -> Image.Image:
        """🚀 Крупная красная плитка с белой ракетой (Высокая производительность)."""
        img = Image.new("RGBA", cls.SIZE, (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)
        draw.rounded_rectangle([1, 1, 62, 62], radius=14, fill="#E84118", outline="#990000", width=2)
        draw.polygon([(8, 46), (22, 30), (22, 44)], fill="#FFFFFF", outline="#4A0E07", width=2)
        draw.polygon([(56, 46), (42, 30), (42, 44)], fill="#FFFFFF", outline="#4A0E07", width=2)
        draw.polygon([(32, 59), (24, 45), (32, 49), (40, 45)], fill="#FFDD00", outline="#FF2200", width=1)
        draw.polygon([(32, 6), (46, 26), (42, 44), (22, 44), (18, 26)], fill="#FFFFFF", outline="#4A0E07", width=2)
        draw.ellipse([26, 17, 38, 29], fill="#00E5FF", outline="#FFFFFF", width=2)
        draw.ellipse([28, 19, 32, 23], fill="#FFFFFF")
        cls._draw_power_badge(draw, is_ac)
        if has_update:
            cls._draw_update_badge(draw)
        return img

    @classmethod
    def draw_tile_car(cls, is_ac: bool, has_update: bool = False) -> Image.Image:
        """🚗 Крупная лазурная плитка с белым автомобилем (Сбалансированный режим)."""
        img = Image.new("RGBA", cls.SIZE, (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)
        draw.rounded_rectangle([1, 1, 62, 62], radius=14, fill="#00A8FF", outline="#0070B8", width=2)
        draw.polygon([(6, 32), (58, 32), (58, 44), (6, 44)], fill="#FFFFFF", outline="#004E82", width=2)
        draw.polygon([(18, 32), (25, 20), (41, 20), (48, 32)], fill="#FFFFFF", outline="#004E82", width=2)
        draw.polygon([(26, 23), (40, 23), (45, 30), (21, 30)], fill="#00A8FF")
        draw.rectangle([54, 34, 58, 38], fill="#FFFA65")
        draw.rectangle([6, 34, 10, 38], fill="#FF3838")
        draw.ellipse([10, 38, 24, 52], fill="#2D3436", outline="#FFFFFF", width=2)
        draw.ellipse([15, 43, 19, 47], fill="#FFFFFF")
        draw.ellipse([40, 38, 54, 52], fill="#2D3436", outline="#FFFFFF", width=2)
        draw.ellipse([45, 43, 49, 47], fill="#FFFFFF")
        cls._draw_power_badge(draw, is_ac)
        if has_update:
            cls._draw_update_badge(draw)
        return img

    @classmethod
    def draw_tile_bicycle(cls, is_ac: bool, has_update: bool = False) -> Image.Image:
        """🚲 Крупная изумрудная плитка с желто-белым велосипедом (Экономия энергии)."""
        img = Image.new("RGBA", cls.SIZE, (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)
        draw.rounded_rectangle([1, 1, 62, 62], radius=14, fill="#00B894", outline="#00755E", width=2)
        draw.ellipse([6, 22, 28, 44], outline="#FFFFFF", width=4, fill="#00755E")
        draw.ellipse([15, 31, 19, 35], fill="#FFFFFF")
        draw.ellipse([36, 22, 58, 44], outline="#FFFFFF", width=4, fill="#00755E")
        draw.ellipse([45, 31, 49, 35], fill="#FFFFFF")
        fc = "#FED330"
        draw.line([(17, 33), (28, 33)], fill=fc, width=4)
        draw.line([(17, 33), (23, 18)], fill=fc, width=4)
        draw.line([(28, 33), (23, 18)], fill=fc, width=4)
        draw.line([(28, 33), (43, 16)], fill=fc, width=4)
        draw.line([(23, 18), (43, 16)], fill=fc, width=4)
        draw.line([(43, 16), (47, 33)], fill=fc, width=4)
        draw.line([(19, 15), (27, 15)], fill="#2D3436", width=4)
        draw.line([(41, 11), (46, 13)], fill="#2D3436", width=4)
        cls._draw_power_badge(draw, is_ac)
        if has_update:
            cls._draw_update_badge(draw)
        return img

    @classmethod
    def draw_tile_icon(cls, plan_type: str, is_ac: bool, has_update: bool = False) -> Image.Image:
        """Сплошная плитка (App Tile) 100% заполнения для максимальной видимости."""
        pt = str(plan_type).lower()
        if (
            "07fa2daf" in pt
            or "high" in pt
            or "perf" in pt
            or "game" in pt
            or "boost" in pt
            or "производит" in pt
        ):
            return cls.draw_tile_rocket(is_ac, has_update)
        elif (
            "d6c42cfd" in pt
            or "saver" in pt
            or "save" in pt
            or "eco" in pt
            or "silent" in pt
            or "idle" in pt
            or "эконом" in pt
        ):
            return cls.draw_tile_bicycle(is_ac, has_update)
        else:
            return cls.draw_tile_car(is_ac, has_update)

    @classmethod
    def _draw_power_badge(cls, draw: ImageDraw.ImageDraw, is_ac: bool) -> None:
        """Отрисовка контрастного микро-бейджа источника питания (в правом нижнем углу 44..62)."""
        if is_ac:
            # 🔌 Сеть 220V: вилка с зубцами на черной подложке
            draw.rectangle([44, 44, 62, 62], fill="#0A3D62", outline="#FFFFFF", width=1)
            # Корпус вилки
            draw.rectangle([48, 50, 58, 58], fill="#FFFFFF")
            # Зубцы вилки
            draw.line([(50, 46), (50, 50)], fill="#FFFFFF", width=2)
            draw.line([(56, 46), (56, 50)], fill="#FFFFFF", width=2)
            # Провод
            draw.line([(53, 58), (53, 62)], fill="#74B9FF", width=2)
        else:
            # 🍃 Батарея: сочный зеленый листик с белой окантовкой
            draw.rectangle([44, 44, 62, 62], fill="#1B4D3E", outline="#FFFFFF", width=1)
            draw.polygon([(46, 58), (54, 46), (60, 52), (54, 60)], fill="#2ECC71")
            draw.line([(48, 56), (56, 49)], fill="#FFFFFF", width=1)

    @classmethod
    def _draw_update_badge(cls, draw: ImageDraw.ImageDraw) -> None:
        """Маркер доступного обновления (оранжевый кружок с белой стрелкой вверх в левом верхнем углу)."""
        draw.ellipse([2, 2, 18, 18], fill="#FF4757", outline="#FFFFFF", width=2)
        # Стрелка вверх
        draw.polygon([(10, 5), (6, 11), (9, 11), (9, 15), (11, 15), (11, 11), (14, 11)], fill="#FFFFFF")

    @classmethod
    def generate_icon(cls, plan_type: str, is_ac: bool, has_update: bool = False) -> Image.Image:
        """Фабричный метод генерации иконки под план питания."""
        pt = str(plan_type).lower()
        if (
            "07fa2daf" in pt
            or "high" in pt
            or "perf" in pt
            or "game" in pt
            or "boost" in pt
            or "производит" in pt
        ):
            return cls.draw_rocket_icon(is_ac, has_update)
        elif (
            "d6c42cfd" in pt
            or "saver" in pt
            or "save" in pt
            or "eco" in pt
            or "silent" in pt
            or "idle" in pt
            or "эконом" in pt
        ):
            return cls.draw_bicycle_icon(is_ac, has_update)
        else:
            return cls.draw_car_icon(is_ac, has_update)
