"""
Currency Conversion Utilities for Gkach and Gourdes
"""
from flask import current_app


def gkach_to_htg(gkach_amount):
    """
    Convert Gkach to Haitian Gourdes (HTG)
    
    Args:
        gkach_amount (int): Amount in Gkach
        
    Returns:
        float: Equivalent amount in HTG
    """
    rate = current_app.config.get('GKACH_TO_HTG_RATE', 1.15)
    return gkach_amount * rate


def htg_to_gkach(htg_amount):
    """
    Convert Haitian Gourdes (HTG) to Gkach
    
    Args:
        htg_amount (float): Amount in HTG
        
    Returns:
        int: Equivalent amount in Gkach (rounded to nearest integer)
    """
    rate = current_app.config.get('GKACH_TO_HTG_RATE', 1.15)
    return round(htg_amount / rate)


def format_htg(amount):
    """
    Format HTG amount for display
    
    Args:
        amount (float): Amount in HTG
        
    Returns:
        str: Formatted HTG string (e.g., "120.00 HTG")
    """
    return f"{amount:.2f} HTG"
