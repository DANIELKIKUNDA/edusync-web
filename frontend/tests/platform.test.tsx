// @vitest-environment jsdom
import React, {useState} from 'react';
import {afterEach, beforeAll, describe, expect, it, vi} from 'vitest';
import {cleanup, render, screen} from '@testing-library/react';
import userEvent from '@testing-library/user-event';

vi.mock('../src/api', () => ({platformStepUp: vi.fn(() => new Promise(() => {})), MfaError: class extends Error {}}));
vi.mock('../src/platform/shell', () => ({initialsOf: () => 'E'}));
vi.mock('../src/platform/updates', () => ({CURRENT_BUILD: 'test', CURRENT_VERSION: '0.0.0-test', shortBuild: () => 'test'}));
vi.mock('../src/messaging_api', () => ({pushConfig: vi.fn(), pushSubscribe: vi.fn(), pushRevoke: vi.fn()}));
vi.mock('@firebase/app',()=>({getApps:()=>[],initializeApp:vi.fn(()=>({name:'test'}))}));
vi.mock('@firebase/messaging',()=>({isSupported:async()=>true,getMessaging:()=>({}),getToken:vi.fn(async()=>'test-device-token-not-a-secret')}));
import {Modal, StepUpDialog} from '../src/platform/account';
import {platformStepUp} from '../src/api';
import {pushConfig, pushRevoke, pushSubscribe} from '../src/messaging_api';
import {disablePush, enablePush, PUSH_ACTIVATION_MESSAGE, rememberedSubscription} from '../src/push_client';

beforeAll(() => Object.defineProperty(window, 'matchMedia', {value: () => ({matches: false, addEventListener() {}, removeEventListener() {}})}));
afterEach(() => {cleanup(); vi.clearAllMocks(); localStorage.clear();});

describe('shared sensitive-action dialog', () => {
  it('keeps focus through parent renders, filters digits and supports Backspace', async () => {
    function Form() {const [v, set] = useState(''); return <Modal title="MFA" onClose={() => {}}><input aria-label="Code" value={v} onChange={e => set(e.target.value.replace(/\D/g, '').slice(0, 6))}/></Modal>;}
    render(<Form/>);
    const input = screen.getByRole('textbox');
    await userEvent.type(input, '12a345');
    expect(document.activeElement).toBe(input);
    expect((input as HTMLInputElement).value).toBe('12345');
    await userEvent.keyboard('{Backspace}6');
    expect((input as HTMLInputElement).value).toBe('12346');
    expect(document.activeElement).toBe(input);
  });
  it('accepts a complete pasted code and submits once', async () => {
    const user = userEvent.setup(); render(<StepUpDialog token="test" onDone={() => {}}/>);
    const input = screen.getByRole('textbox');
    expect(input.getAttribute('inputmode')).toBe('numeric');
    expect(input.getAttribute('autocomplete')).toBe('one-time-code');
    await user.click(input); await user.paste('123456'); await user.keyboard('{Enter}');
    expect(platformStepUp).toHaveBeenCalledExactlyOnceWith('test', '123456');
  });
  it('uses the latest close handler and restores focus only on unmount', async () => {
    const trigger = document.createElement('button'); document.body.append(trigger); trigger.focus();
    const first = vi.fn(), latest = vi.fn();
    const view = render(<Modal title="Test" onClose={first}><input/></Modal>);
    view.rerender(<Modal title="Test" onClose={latest}><input/></Modal>);
    await userEvent.keyboard('{Escape}'); expect(first).not.toHaveBeenCalled(); expect(latest).toHaveBeenCalledOnce();
    view.unmount(); expect(document.activeElement).toBe(trigger); trigger.remove();
  });
});

describe('push activation', () => {
  function support(permission: NotificationPermission) {
    Object.defineProperty(navigator, 'serviceWorker', {value: {}, configurable: true});
    Object.defineProperty(window, 'PushManager', {value: class {}, configurable: true});
    Object.defineProperty(window, 'Notification', {value: {permission, requestPermission: vi.fn(async () => permission)}, configurable: true});
  }
  it('never exposes raw network errors or logs credentials', async () => {
    support('granted'); vi.mocked(pushConfig).mockRejectedValueOnce(new TypeError('Failed to fetch secret-token'));
    const log = vi.spyOn(console, 'warn').mockImplementation(() => {});
    await expect(enablePush('private', 'platform', true)).rejects.toThrow(PUSH_ACTIVATION_MESSAGE);
    expect(JSON.stringify(log.mock.calls)).not.toMatch(/secret-token|private|Failed to fetch/);
    expect(pushSubscribe).not.toHaveBeenCalled(); log.mockRestore();
  });
  it('does not register a device when permission is denied', async () => {
    support('denied'); vi.mocked(pushConfig).mockResolvedValueOnce({provider: 'fake'} as never);
    const log = vi.spyOn(console, 'warn').mockImplementation(() => {});
    await expect(enablePush('test', 'platform', true)).rejects.toThrow(PUSH_ACTIVATION_MESSAGE);
    expect(pushSubscribe).not.toHaveBeenCalled(); log.mockRestore();
  });
  it('retains only the server subscription identifier after registration', async () => {
    support('granted'); vi.mocked(pushConfig).mockResolvedValueOnce({provider: 'fake'} as never);
    vi.mocked(pushSubscribe).mockResolvedValueOnce({id: 'device-1'} as never);
    await enablePush('test', 'platform', true);
    expect(rememberedSubscription('platform')).toBe('device-1');
    expect(localStorage.length).toBe(1); expect(Notification.requestPermission).not.toHaveBeenCalled();
  });
  it('registers the existing Firebase device token again without creating local duplicates',async()=>{
    support('granted');
    const registration={scope:location.origin+'/',active:{scriptURL:location.origin+'/sw.js'}};
    Object.defineProperty(navigator,'serviceWorker',{value:{ready:Promise.resolve(registration)},configurable:true});
    vi.mocked(pushConfig).mockResolvedValue({provider:'fcm',web_config:{projectId:'test'},vapid_public_key:'public-test-key'});
    vi.mocked(pushSubscribe).mockResolvedValue({id:'existing-device',status:'already_subscribed'});
    await enablePush('test','platform',true);await enablePush('test','platform',true);
    expect(pushSubscribe).toHaveBeenCalledTimes(2);
    expect(rememberedSubscription('platform')).toBe('existing-device');
    expect(localStorage.length).toBe(1);
    expect(JSON.stringify({...localStorage})).not.toContain('test-device-token');
  });
  it('does not claim revocation when the server could not confirm it',async()=>{
    support('granted');vi.mocked(pushConfig).mockResolvedValueOnce({provider:'fake'} as never);
    vi.mocked(pushSubscribe).mockResolvedValueOnce({id:'active-device',status:'subscribed'});
    await enablePush('test','platform',true);
    vi.mocked(pushRevoke).mockRejectedValueOnce(new TypeError('network'));
    await expect(disablePush('test','platform',true)).rejects.toThrow();
    expect(rememberedSubscription('platform')).toBe('active-device');
  });
});
