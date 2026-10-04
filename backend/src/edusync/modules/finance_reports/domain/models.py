from dataclasses import dataclass
from datetime import date,timedelta

SYSTEM_TEMPLATES=(
 {'code':'DAILY_CASH','label':'Rapport journalier de caisse','scope_mode':'MY_CASH','sections':['cash_summary','collections_by_category','movements']},
 {'code':'CASH_JOURNAL','label':'Journal des mouvements','scope_mode':'MY_CASH','sections':['movements']},
 {'code':'COLLECTIONS','label':'Situation des encaissements','scope_mode':'ALL_CASHIERS','sections':['collections_by_category','origin_years']},
 {'code':'CONSOLIDATED_CASH','label':'Situation consolidée des caisses','scope_mode':'ALL_CASHIERS','sections':['cash_summary','cashiers']},
)
ALLOWED_SECTIONS={'cash_summary','collections_by_category','movements','origin_years','cashiers','product_sales','old_debts'}

def period_bounds(kind:str, today:date, start:date|None=None,end:date|None=None):
 if kind=='TODAY': return today,today
 if kind=='WEEK': return today-timedelta(days=today.weekday()),today
 if kind=='MONTH': return today.replace(day=1),today
 if kind=='CUSTOM' and start and end and start<=end:return start,end
 raise ValueError('Période de rapport invalide')

def validate_sections(items:list[str]):
 bad=set(items)-ALLOWED_SECTIONS
 if bad: raise ValueError('Rubrique de rapport inconnue: '+', '.join(sorted(bad)))
 return list(dict.fromkeys(items))
