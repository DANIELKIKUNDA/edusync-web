/** A UI continuity hint only. The server remains the authority for every request.
 * Tokens are kept in memory and never logged or persisted by this helper. */
export function hasUsableAccessToken(token:string,now=Date.now()):boolean{
  try{
    const part=token.split('.')[1];
    if(!part)return false;
    const claims=JSON.parse(atob(part.replace(/-/g,'+').replace(/_/g,'/')));
    return typeof claims.exp==='number'&&Number.isFinite(claims.exp)&&claims.exp*1000>now+5_000;
  }catch{return false}
}
