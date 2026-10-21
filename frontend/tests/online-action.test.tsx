// @vitest-environment jsdom
import React from 'react';
import {cleanup,render,screen,act} from '@testing-library/react';
import {afterEach,expect,it,vi} from 'vitest';
import userEvent from '@testing-library/user-event';
import {OnlineActionButton} from '../src/platform/online_action';
import {clearPlatformContext,rememberPlatformContext,setPlatformAuthState} from '../src/platform/offline_session';
afterEach(()=>{cleanup();clearPlatformContext();});
it('disables a sensitive action while offline and restores it after authenticated recovery',async()=>{
  rememberPlatformContext({user:{id:'user',full_name:'Test',email:'test@example.test'},menu:[],permissions:[],roles:[]});
  const action=vi.fn();render(<OnlineActionButton onClick={action}>Créer une école</OnlineActionButton>);
  act(()=>setPlatformAuthState('OFFLINE_AUTHENTICATED_CACHED'));
  const button=screen.getByRole('button');expect((button as HTMLButtonElement).disabled).toBe(true);
  await userEvent.click(button);expect(action).not.toHaveBeenCalled();
  act(()=>setPlatformAuthState('ONLINE_AUTHENTICATED'));
  await userEvent.click(button);expect(action).toHaveBeenCalledOnce();
});
