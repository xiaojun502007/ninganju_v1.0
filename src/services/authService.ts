const API_BASE_URL = "http://127.0.0.1:8787";

type AuthResponse = {
  ok: boolean;
  message: string;
  sessionToken?: string;
  user?: {
    id: number;
    username: string;
    role: "user" | "admin";
  };
};

async function postAuth(path: string, payload: Record<string, string>) {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json"
    },
    body: JSON.stringify(payload)
  });

  const data = (await response.json()) as AuthResponse;
  if (!response.ok || !data.ok) {
    throw new Error(data.message || "请求失败，请稍后重试");
  }
  return data;
}

export async function registerUser(username: string, password: string) {
  return postAuth("/api/register", { username, password });
}

export async function loginUser(username: string, password: string) {
  return postAuth("/api/login", { username, password });
}

export async function changePassword(
  username: string,
  currentPassword: string,
  newPassword: string,
  confirmPassword: string
) {
  return postAuth("/api/change-password", { username, currentPassword, newPassword, confirmPassword });
}
