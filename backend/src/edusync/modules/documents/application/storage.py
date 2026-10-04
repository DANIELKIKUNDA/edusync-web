from __future__ import annotations
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
import re

_BAD=re.compile(r'[<>:"/\\|?*\x00-\x1f]')
def safe_segment(value:str)->str:
    value=_BAD.sub('_',value).strip().strip('.')
    return value or 'non-classe'

@dataclass(frozen=True,slots=True)
class DocumentLocation:
    school_id:str; academic_year:str; module:str; category:str; filename:str
    @property
    def logical_key(self)->str:
        parts=('schools',self.school_id,self.academic_year,self.module,self.category,self.filename)
        return '/'.join(safe_segment(x) for x in parts)

class LocalObjectStorageAdapter:
    """Dev/test adapter. A logical key is stable: writing again replaces only the current object.
    Immutable generation evidence remains in PostgreSQL; production can swap this for S3."""
    def __init__(self,root:Path): self.root=Path(root)
    def put_current(self,key:str,data:bytes)->tuple[str,int]:
        target=self.root.joinpath(*key.split('/')); target.parent.mkdir(parents=True,exist_ok=True)
        tmp=target.with_suffix(target.suffix+'.tmp'); tmp.write_bytes(data); tmp.replace(target)
        return sha256(data).hexdigest(),len(data)
    def read(self,key:str)->bytes: return self.root.joinpath(*key.split('/')).read_bytes()
