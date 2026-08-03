from sys import set_coroutine_origin_tracking_depth
import cantools

db = cantools.database.load_file('ARS408.dbc')
# for msg in db.messages:
#     print(msg.name)

# for signal in msg.signals:
#     print(signal.name)

def send_radar_configuration(rcs_threshold_valid=0, rcs_threshold=0, store_in_nvm_valid=0, 
                           sort_index_valid=0, sort_index=0, store_in_nvm=1, 
                           send_ext_info_valid=0, send_ext_info=1, ctrl_relay_valid=0, 
                           ctrl_relay=1, send_quality_valid=0, send_quality=1, 
                           max_distance_valid=0, radar_power_valid=0, output_type_valid=0, 
                           sensor_id_valid=0, max_distance=100, radar_power=7, 
                           output_type=0, sensor_id=0):
    """
    发送RadarConfiguration配置消息
    
    参数:
        rcs_threshold_valid: RadarCfg_RCS_Threshold_Valid信号值 (0-1)
        rcs_threshold: RadarCfg_RCS_Threshold信号值 (0-7)
        store_in_nvm_valid: RadarCfg_StoreInNVM_valid信号值 (0-1)
        sort_index_valid: RadarCfg_SortIndex_valid信号值 (0-1)
        sort_index: RadarCfg_SortIndex信号值 (0-7)
        store_in_nvm: RadarCfg_StoreInNVM信号值 (0-1)
        send_ext_info_valid: RadarCfg_SendExtInfo_valid信号值 (0-1)
        send_ext_info: RadarCfg_SendExtInfo信号值 (0-1)
        ctrl_relay_valid: RadarCfg_CtrlRelay_valid信号值 (0-1)
        ctrl_relay: RadarCfg_CtrlRelay信号值 (0-1)
        send_quality_valid: RadarCfg_SendQuality_valid信号值 (0-1)
        send_quality: RadarCfg_SendQuality信号值 (0-1)
        max_distance_valid: RadarCfg_MaxDistance_valid信号值 (0-1)
        radar_power_valid: RadarCfg_RadarPower_valid信号值 (0-1)
        output_type_valid: RadarCfg_OutputType_valid信号值 (0-1)
        sensor_id_valid: RadarCfg_SensorID_valid信号值 (0-1)
        max_distance: RadarCfg_MaxDistance信号值 (0-2046, 单位: m)
        radar_power: RadarCfg_RadarPower信号值 (0-7)
        output_type: RadarCfg_OutputType信号值 (0-2)
        sensor_id: RadarCfg_SensorID信号值 (0-7)
    
    返回:
        编码后的消息数据和消息ID
    """
    # 获取RadarConfiguration消息定义
    radar_config_msg = db.get_message_by_name('RadarConfiguration')
    
    # 准备信号值字典
    signals = {
        'RadarCfg_RCS_Threshold_Valid': rcs_threshold_valid,
        'RadarCfg_RCS_Threshold': rcs_threshold,
        'RadarCfg_StoreInNVM_valid': store_in_nvm_valid,
        'RadarCfg_SortIndex_valid': sort_index_valid,
        'RadarCfg_SortIndex': sort_index,
        'RadarCfg_StoreInNVM': store_in_nvm,
        'RadarCfg_SendExtInfo_valid': send_ext_info_valid,
        'RadarCfg_SendExtInfo': send_ext_info,
        'RadarCfg_CtrlRelay_valid': ctrl_relay_valid,
        'RadarCfg_CtrlRelay': ctrl_relay,
        'RadarCfg_SendQuality_valid': send_quality_valid,
        'RadarCfg_SendQuality': send_quality,
        'RadarCfg_MaxDistance_valid': max_distance_valid,
        'RadarCfg_RadarPower_valid': radar_power_valid,
        'RadarCfg_OutputType_valid': output_type_valid,
        'RadarCfg_SensorID_valid': sensor_id_valid,
        'RadarCfg_MaxDistance': max_distance,
        'RadarCfg_RadarPower': radar_power,
        'RadarCfg_OutputType': output_type,
        'RadarCfg_SensorID': sensor_id
    }
    
    # 编码消息
    data = radar_config_msg.encode(signals)
    
    # 打印编码结果（实际项目中这里应该是发送CAN消息的代码）
    #print(f"发送RadarConfiguration消息 (ID: {radar_config_msg.frame_id})")
    print(f"编码数据: {data.hex()}")
    #print(f"信号值: {signals}")
    
    return radar_config_msg.frame_id, data

def send_filter_configuration(filter_type, index, active, valid, 
                             min_value, max_value):
    """
    发送FilterCfg过滤配置消息
    
    参数:
        filter_type: FilterCfg_Type信号值 (0-1)
        index: FilterCfg_Index信号值 (0-15) - 多路复用信号，对应不同的过滤参数
        active: FilterCfg_Active信号值 (0-1)
        valid: FilterCfg_Valid信号值 (0-1)
        min_value: 最小过滤值（根据index对应不同参数）
        max_value: 最大过滤值（根据index对应不同参数）
    
    index值对应关系:
        0: NofObj (目标数量)
        1: Distance (距离)
        2: Azimuth (方位角)
        3: VrelOncome (迎面相对速度)
        4: VrelDepart (背离相对速度)
        5: RCS (雷达截面积)
        6: Lifetime (生命周期)
        7: Size (大小)
        8: ProbExists (存在概率)
        9: Y (横向位置)
        10: X (纵向位置)
        11: VYLeftRight (横向速度-左右)
        12: VXOncome (纵向速度-迎面)
        13: VYRightLeft (横向速度-右左)
        14: VXDepart (纵向速度-背离)
    
    返回:
        编码后的消息数据和消息ID
    """
    # 获取FilterCfg消息定义
    filter_cfg_msg = db.get_message_by_name('FilterCfg')
    
    # 准备信号值字典
    signals = {
        'FilterCfg_Type': filter_type,
        'FilterCfg_Index': index,
        'FilterCfg_Active': active,
        'FilterCfg_Valid': valid
    }
    
    # 根据index值添加相应的过滤参数信号
    index_signal_map = {
        0: ('FilterCfg_Min_NofObj', 'FilterCfg_Max_NofObj'),
        1: ('FilterCfg_Min_Distance', 'FilterCfg_Max_Distance'),
        2: ('FilterCfg_Min_Azimuth', 'FilterCfg_Max_Azimuth'),
        3: ('FilterCfg_Min_VrelOncome', 'FilterCfg_Max_VrelOncome'),
        4: ('FilterCfg_Min_VrelDepart', 'FilterCfg_Max_VrelDepart'),
        5: ('FilterCfg_Min_RCS', 'FilterCfg_Max_RCS'),
        6: ('FilterCfg_Min_Lifetime', 'FilterCfg_Max_Lifetime'),
        7: ('FilterCfg_Min_Size', 'FilterCfg_Max_Size'),
        8: ('FilterCfg_Min_ProbExists', 'FilterCfg_Max_ProbExists'),
        9: ('FilterCfg_Min_Y', 'FilterCfg_Max_Y'),
        10: ('FilterCfg_Min_X', 'FilterCfg_Max_X'),
        11: ('FilterCfg_Min_VYLeftRight', 'FilterCfg_Max_VYLeftRight'),
        12: ('FilterCfg_Min_VXOncome', 'FilterCfg_Max_VXOncome'),
        13: ('FilterCfg_Min_VYRightLeft', 'FilterCfg_Max_VYRightLeft'),
        14: ('FilterCfg_Min_VXDepart', 'FilterCfg_Max_VXDepart')
    }
    
    if index in index_signal_map:
        min_signal, max_signal = index_signal_map[index]
        signals[min_signal] = min_value
        signals[max_signal] = max_value
    
    # 编码消息
    data = filter_cfg_msg.encode(signals)
    
    # 打印编码结果（实际项目中这里应该是发送CAN消息的代码）
    #print(f"发送FilterCfg消息 (ID: {hex(filter_cfg_msg.frame_id)})")
    #print(f"编码数据: {data.hex(" ")}")
    print("panda.can_send(0x202, "+ f"{data}" + ",1)")
    #print(f"信号值: {signals}")
    
    return filter_cfg_msg.frame_id, data

# 示例用法
if __name__ == "__main__":
    # 发送自定义配置
    print("\n发送自定义配置:")
    send_radar_configuration(rcs_threshold_valid = 1, rcs_threshold=0, sort_index_valid=0,
                             sort_index=1, send_ext_info=1, max_distance_valid=0, max_distance=800,
                             output_type_valid=0, output_type=1, radar_power_valid=0, radar_power=0)
    
    # 发送自定义过滤配置 - 设置距离过滤
    #print("\n发送自定义过滤配置 (距离过滤):")
    #send_filter_configuration(filter_type=1, active=0, valid=1, index=1, min_value=0, max_value=300)
