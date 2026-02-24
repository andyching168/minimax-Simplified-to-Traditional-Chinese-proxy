"""
簡體中文轉繁體中文轉換器
使用 OpenCC 進行高品質的簡繁轉換
"""

from opencc import OpenCC
import re
import json
from typing import Any


class TraditionalChineseConverter:
    """簡體中文轉繁體中文的轉換器"""
    
    def __init__(self, config: str = "s2twp"):
        """
        初始化轉換器
        
        Args:
            config: OpenCC 配置
                - s2t: 簡體到繁體
                - s2tw: 簡體到台灣正體
                - s2twp: 簡體到台灣正體並轉換詞彙（推薦）
                - s2hk: 簡體到香港繁體
        """
        self.converter = OpenCC(config)
    
    def convert(self, text: str) -> str:
        """
        將簡體中文轉換為繁體中文
        
        Args:
            text: 輸入的簡體中文文字
            
        Returns:
            轉換後的繁體中文文字
        """
        if not text:
            return text
        return self.converter.convert(text)
    
    def convert_preserve_code(self, text: str) -> str:
        """
        轉換文字，但保留程式碼區塊不轉換
        
        Args:
            text: 輸入的文字
            
        Returns:
            轉換後的文字，程式碼區塊保持原樣
        """
        if not text:
            return text
        
        # 保護 code blocks (```...``` 和 `...`)
        code_blocks: list[tuple[str, str]] = []
        
        # 先處理多行程式碼區塊
        def save_code_block(match: re.Match) -> str:
            placeholder = f"__CODE_BLOCK_{len(code_blocks)}__"
            code_blocks.append((placeholder, match.group(0)))
            return placeholder
        
        # 保護 ```...``` 區塊
        text = re.sub(r'```[\s\S]*?```', save_code_block, text)
        
        # 保護 `...` 行內程式碼
        text = re.sub(r'`[^`]+`', save_code_block, text)
        
        # 保護 XML/HTML 標籤內的屬性
        text = re.sub(r'<[^>]+>', save_code_block, text)
        
        # 進行簡繁轉換
        text = self.convert(text)
        
        # 還原程式碼區塊
        for placeholder, original in code_blocks:
            text = text.replace(placeholder, original)
        
        return text
    
    def convert_dict(self, data: dict[str, Any]) -> dict[str, Any]:
        """
        遞迴轉換字典中的所有字串值
        
        Args:
            data: 輸入的字典
            
        Returns:
            轉換後的字典
        """
        result = {}
        for key, value in data.items():
            if isinstance(value, str):
                result[key] = self.convert_preserve_code(value)
            elif isinstance(value, dict):
                result[key] = self.convert_dict(value)
            elif isinstance(value, list):
                result[key] = self.convert_list(value)
            else:
                result[key] = value
        return result
    
    def convert_list(self, data: list[Any]) -> list[Any]:
        """
        遞迴轉換列表中的所有字串值
        
        Args:
            data: 輸入的列表
            
        Returns:
            轉換後的列表
        """
        result = []
        for item in data:
            if isinstance(item, str):
                result.append(self.convert_preserve_code(item))
            elif isinstance(item, dict):
                result.append(self.convert_dict(item))
            elif isinstance(item, list):
                result.append(self.convert_list(item))
            else:
                result.append(item)
        return result


# 建立全域轉換器實例
converter = TraditionalChineseConverter("s2twp")


def to_traditional(text: str) -> str:
    """
    簡單的簡繁轉換函式
    
    Args:
        text: 輸入的簡體中文文字
        
    Returns:
        轉換後的繁體中文文字
    """
    return converter.convert_preserve_code(text)


def to_traditional_json(data: dict | list) -> dict | list:
    """
    轉換 JSON 資料中的所有文字
    
    Args:
        data: 輸入的 JSON 資料（字典或列表）
        
    Returns:
        轉換後的 JSON 資料
    """
    if isinstance(data, dict):
        return converter.convert_dict(data)
    elif isinstance(data, list):
        return converter.convert_list(data)
    return data
