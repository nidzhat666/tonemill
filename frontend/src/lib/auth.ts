/** Whether an HTTP `Authorization: Basic` header decodes to the given username/password. */
export function checkBasicAuth(
	authorizationHeader: string | null,
	username: string,
	password: string
): boolean {
	if (!authorizationHeader?.startsWith('Basic ')) return false;

	let decoded: string;
	try {
		decoded = atob(authorizationHeader.slice('Basic '.length));
	} catch {
		return false;
	}

	const separatorIndex = decoded.indexOf(':');
	if (separatorIndex === -1) return false;

	const providedUsername = decoded.slice(0, separatorIndex);
	const providedPassword = decoded.slice(separatorIndex + 1);
	return providedUsername === username && providedPassword === password;
}
