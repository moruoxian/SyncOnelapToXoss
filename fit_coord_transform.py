"""
FIT 文件坐标系转换模块
将 FIT 文件中的 GPS 坐标从 GCJ-02（火星坐标系）转换为 WGS84（国际标准坐标系）

适用于：OneLap（顽鹿）下载的 FIT 文件同步到 Strava 等国际平台前做坐标修正

依赖：garmin-fit-sdk (pip install garmin-fit-sdk)
"""

import math
import os
import tempfile
import logging

logger = logging.getLogger(__name__)

# ============================================================
# GCJ-02 <-> WGS84 坐标转换算法
# 来源: coordTransform_py (wandergis/coordTransform_py) 标准实现
# ============================================================

pi = 3.1415926535897932384626
a = 6378245.0           # 长半轴
ee = 0.00669342162296594323  # 偏心率平方

# FIT 坐标单位转换常量
SEMICIRCLES_TO_DEGREES = 180.0 / (2 ** 31)
DEGREES_TO_SEMICIRCLES = (2 ** 31) / 180.0


def _out_of_china(lng, lat):
    """判断是否在国内（粗略判断），不在国内不做偏移"""
    return not (73.66 < lng < 135.05 and 3.86 < lat < 53.55)


def _transform_lat(lng, lat):
    ret = -100.0 + 2.0 * lng + 3.0 * lat + 0.2 * lat * lat + \
          0.1 * lng * lat + 0.2 * math.sqrt(math.fabs(lng))
    ret += (20.0 * math.sin(6.0 * lng * pi) + 20.0 * math.sin(2.0 * lng * pi)) * 2.0 / 3.0
    ret += (20.0 * math.sin(lat * pi) + 40.0 * math.sin(lat / 3.0 * pi)) * 2.0 / 3.0
    ret += (160.0 * math.sin(lat / 12.0 * pi) + 320 * math.sin(lat * pi / 30.0)) * 2.0 / 3.0
    return ret


def _transform_lng(lng, lat):
    ret = 300.0 + lng + 2.0 * lat + 0.1 * lng * lng + \
          0.1 * lng * lat + 0.1 * math.sqrt(math.fabs(lng))
    ret += (20.0 * math.sin(6.0 * lng * pi) + 20.0 * math.sin(2.0 * lng * pi)) * 2.0 / 3.0
    ret += (20.0 * math.sin(lng * pi) + 40.0 * math.sin(lng / 3.0 * pi)) * 2.0 / 3.0
    ret += (150.0 * math.sin(lng / 12.0 * pi) + 300.0 * math.sin(lng / 30.0 * pi)) * 2.0 / 3.0
    return ret


def gcj02_to_wgs84(lng, lat):
    """GCJ-02 坐标转 WGS84 坐标（经度, 纬度）"""
    if _out_of_china(lng, lat):
        return lng, lat
    dlat = _transform_lat(lng - 105.0, lat - 35.0)
    dlng = _transform_lng(lng - 105.0, lat - 35.0)
    radlat = lat / 180.0 * pi
    magic = math.sin(radlat)
    magic = 1 - ee * magic * magic
    sqrtmagic = math.sqrt(magic)
    dlat = (dlat * 180.0) / ((a * (1 - ee)) / (magic * sqrtmagic) * pi)
    dlng = (dlng * 180.0) / (a / sqrtmagic * math.cos(radlat) * pi)
    mglat = lat + dlat
    mglng = lng + dlng
    return lng * 2 - mglng, lat * 2 - mglat


def _semicircles_to_degrees(semicircles):
    """FIT semicircles 转度数"""
    return semicircles * SEMICIRCLES_TO_DEGREES


def _degrees_to_semicircles(degrees):
    """度数转 FIT semicircles"""
    return int(round(degrees * DEGREES_TO_SEMICIRCLES))


def _convert_position_pair(lat_semi, lng_semi):
    """转换单个坐标对：semicircles(GCJ-02) -> semicircles(WGS84)

    Returns:
        (new_lat_semi, new_lng_semi) 或 None（如果坐标不在国内无需转换）
    """
    if lat_semi is None or lng_semi is None:
        return None
    lat_deg = _semicircles_to_degrees(lat_semi)
    lng_deg = _semicircles_to_degrees(lng_semi)
    wgs_lng, wgs_lat = gcj02_to_wgs84(lng_deg, lat_deg)
    return _degrees_to_semicircles(wgs_lat), _degrees_to_semicircles(wgs_lng)


# ============================================================
# FIT 文件读写与坐标转换
# ============================================================

# FIT 消息编号常量
MESG_NUM_FILE_ID = 0
MESG_NUM_SESSION = 18
MESG_NUM_LAP = 19
MESG_NUM_RECORD = 20
MESG_NUM_ACTIVITY = 34
MESG_NUM_COURSE_POINT = 32

# 需要转换的坐标字段名 -> (lat_field, lng_field) 对
# 不同消息类型中坐标字段的命名
POSITION_FIELD_PAIRS = [
    ('position_lat', 'position_long'),
    ('start_position_lat', 'start_position_long'),
    ('end_position_lat', 'end_position_long'),
    ('nec_lat', 'nec_long'),       # 东北角边界框
    ('swc_lat', 'swc_long'),       # 西南角边界框
]

# 需要检查坐标的消息类型
MESSAGES_WITH_POSITION = {
    MESG_NUM_RECORD,
    MESG_NUM_LAP,
    MESG_NUM_SESSION,
    MESG_NUM_ACTIVITY,
    MESG_NUM_COURSE_POINT,
}


def _has_garmin_fit_sdk():
    """检查 garmin-fit-sdk 是否可用"""
    try:
        import garmin_fit_sdk  # noqa: F401
        return True
    except ImportError:
        return False


def convert_fit_gcj02_to_wgs84(input_path, output_path=None):
    """将 FIT 文件中的坐标从 GCJ-02 转换为 WGS84

    Args:
        input_path: 输入 FIT 文件路径
        output_path: 输出 FIT 文件路径（None 则自动生成临时文件）

    Returns:
        str: 转换后的文件路径，如果转换失败或不需要转换则返回 input_path
    """
    if not _has_garmin_fit_sdk():
        logger.warning('[FitTransform] garmin-fit-sdk 未安装，跳过坐标转换')
        return input_path

    if not input_path.lower().endswith('.fit'):
        logger.debug(f'[FitTransform] 非 FIT 文件，跳过转换: {os.path.basename(input_path)}')
        return input_path

    from garmin_fit_sdk import Decoder, Encoder
    from garmin_fit_sdk.stream import Stream

    # 自动生成输出路径
    if output_path is None:
        input_dir = os.path.dirname(input_path)
        input_name = os.path.basename(input_path)
        name, ext = os.path.splitext(input_name)
        output_path = os.path.join(input_dir, f'{name}_wgs84{ext}')

    try:
        # 读取 FIT 文件
        stream = Stream.from_file(input_path)
        decoder = Decoder(stream)

        messages = []
        result, errors = decoder.read(
            mesg_listener=lambda mesg_num, mesg: messages.append((mesg_num, mesg)),
        )

        if errors:
            logger.warning(f'[FitTransform] FIT 文件解析有警告: {errors}')
            # 如果有解析错误但仍读取到消息，继续处理

        if not messages:
            logger.warning(f'[FitTransform] 未读取到任何消息，使用原始文件: {os.path.basename(input_path)}')
            return input_path

        # 转换坐标
        converted_count = 0
        skipped_count = 0

        for i, (mesg_num, mesg) in enumerate(messages):
            if mesg_num not in MESSAGES_WITH_POSITION:
                continue

            for lat_field, lng_field in POSITION_FIELD_PAIRS:
                if lat_field in mesg and lng_field in mesg:
                    lat_val = mesg[lat_field]
                    lng_val = mesg[lng_field]
                    if lat_val is None or lng_val is None:
                        continue
                    new_pos = _convert_position_pair(lat_val, lng_val)
                    if new_pos is not None:
                        new_lat, new_lng = new_pos
                        # 检查坐标是否实际发生了变化（即在中国境内）
                        if new_lat != lat_val or new_lng != lng_val:
                            mesg[lat_field] = new_lat
                            mesg[lng_field] = new_lng
                            converted_count += 1
                        else:
                            skipped_count += 1

        if converted_count == 0:
            logger.info(f'[FitTransform] 文件内无中国境内坐标需要转换: {os.path.basename(input_path)}')
            return input_path

        logger.info(f'[FitTransform] 坐标转换完成: {os.path.basename(input_path)} '
                     f'转换 {converted_count} 个点, 境外跳过 {skipped_count} 个点')

        # 写入新的 FIT 文件
        encoder = Encoder()
        for mesg_num, mesg in messages:
            encoder.on_mesg(mesg_num, mesg)
        output_data = encoder.close()

        with open(output_path, 'wb') as f:
            f.write(output_data)

        logger.debug(f'[FitTransform] 转换后文件: {output_path} ({len(output_data)} bytes)')
        return output_path

    except Exception as e:
        logger.error(f'[FitTransform] FIT 坐标转换失败: {e}')
        import traceback
        logger.debug(traceback.format_exc())
        return input_path


def get_strava_upload_path(file_path, enable_conversion=True):
    """获取 Strava 上传用的文件路径（按需转换坐标）

    Args:
        file_path: 原始文件路径
        enable_conversion: 是否启用 GCJ-02 -> WGS84 转换

    Returns:
        str: 实际用于上传的文件路径（可能是转换后的临时文件）
    """
    if not enable_conversion:
        return file_path

    if not file_path.lower().endswith('.fit'):
        return file_path

    # 转换到临时文件
    temp_dir = tempfile.gettempdir()
    base_name = os.path.basename(file_path)
    name, ext = os.path.splitext(base_name)
    temp_output = os.path.join(temp_dir, f'{name}_wgs84{ext}')

    result = convert_fit_gcj02_to_wgs84(file_path, temp_output)
    return result


def cleanup_temp_file(file_path, original_path):
    """清理转换产生的临时文件（如果 file_path 与 original_path 不同）"""
    if file_path != original_path and os.path.exists(file_path):
        try:
            os.remove(file_path)
            logger.debug(f'[FitTransform] 已清理临时文件: {os.path.basename(file_path)}')
        except Exception:
            pass
