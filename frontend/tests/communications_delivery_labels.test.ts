import {describe, expect, it} from 'vitest';
import {deliveryErrorLabel, deliveryStatusLabel} from '../src/messaging_api';

describe('libellés métier de livraison des notifications', () => {
  it('explique en français un appareil push absent', () => {
    expect(deliveryStatusLabel('PUSH', 'CANCELLED', 'NO_PUSH_DEVICE')).toBe('Push non remis');
    expect(deliveryErrorLabel('NO_PUSH_DEVICE')).toBe('Aucun appareil du destinataire n’a activé les notifications');
  });

  it('explique un canal désactivé sans exposer le code technique', () => {
    expect(deliveryStatusLabel('PUSH', 'CANCELLED', 'CHANNEL_DISABLED')).toBe('Push non envoyé');
    expect(deliveryErrorLabel('CHANNEL_DISABLED')).toBe('Ce canal est désactivé pour l’école');
  });

  it('ne révèle pas un nouveau code interne inconnu', () => {
    expect(deliveryErrorLabel('SOME_NEW_INTERNAL_CODE')).toBe('Incident technique à vérifier');
  });
});
