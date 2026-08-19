import { describe, expect, test } from 'vitest';
import { checkBasicAuth } from './auth';

const encode = (credentials: string) => `Basic ${btoa(credentials)}`;

describe('checkBasicAuth', () => {
	test('rejects a missing Authorization header', () => {
		// Given no Authorization header
		// When checking credentials
		// Then access is refused
		expect(checkBasicAuth(null, 'nidzhat', 'secret')).toBe(false);
	});

	test('rejects a non-Basic Authorization header', () => {
		// Given an Authorization header that isn't the Basic scheme
		// When checking credentials
		// Then access is refused
		expect(checkBasicAuth('Bearer some-token', 'nidzhat', 'secret')).toBe(false);
	});

	test('rejects malformed base64 in the Basic header', () => {
		// Given a Basic header whose payload isn't valid base64
		// When checking credentials
		// Then access is refused rather than throwing
		expect(checkBasicAuth('Basic not-valid-base64!!!', 'nidzhat', 'secret')).toBe(false);
	});

	test('rejects wrong credentials', () => {
		// Given a correctly formed Basic header with the wrong password
		// When checking credentials
		// Then access is refused
		expect(checkBasicAuth(encode('nidzhat:wrong-password'), 'nidzhat', 'secret')).toBe(false);
	});

	test('accepts the correct credentials', () => {
		// Given a correctly formed Basic header with the right username/password
		// When checking credentials
		// Then access is granted
		expect(checkBasicAuth(encode('nidzhat:secret'), 'nidzhat', 'secret')).toBe(true);
	});
});
