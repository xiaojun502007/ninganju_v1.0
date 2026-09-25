import { FormEvent, useState } from "react";
import { changePassword, loginUser, registerUser } from "../services/authService";

type LoginPageProps = {
  onLogin: (username: string, role: "user" | "admin", sessionToken: string) => void;
};

export function LoginPage({ onLogin }: LoginPageProps) {
  const [loginUsername, setLoginUsername] = useState("xiaoning");
  const [loginPassword, setLoginPassword] = useState("12345678");
  const [rememberMe, setRememberMe] = useState(true);
  const [passwordVisible, setPasswordVisible] = useState(false);
  const [loginMessage, setLoginMessage] = useState("");
  const [registerOpen, setRegisterOpen] = useState(false);
  const [changePasswordOpen, setChangePasswordOpen] = useState(false);
  const [passwordChangeNotice, setPasswordChangeNotice] = useState("");

  const handleLogin = async (event: FormEvent) => {
    event.preventDefault();
    setLoginMessage("");

    try {
      const result = await loginUser(loginUsername.trim(), loginPassword);
      onLogin(result.user?.username || loginUsername.trim(), result.user?.role || "user", result.sessionToken || "");
    } catch (error) {
      setLoginMessage(error instanceof Error ? error.message : "登录失败，请稍后重试");
    }
  };

  const fillAdminAccount = () => {
    setLoginUsername("administrator");
    setLoginPassword("220250246@xj");
    setLoginMessage("");
  };

  return (
    <section className="login-page">
      <div className="hero-copy">
        <h1>
          让来宁租房<span>更轻松</span>
        </h1>
        <p>基于通勤、生活配套与预算的智能推荐，帮你快速找到理想租住片区。</p>

        <div className="hero-benefits">
          <Benefit icon="pin" title="智能推荐片区" text="结合通勤时长、生活配套与租金预算，精准推荐最优片区" />
          <Benefit icon="briefcase" title="通勤与生活圈评估" text="多维度评估片区通勤效率与生活便利，住得近也要过得好" />
          <Benefit icon="clock" title="历史记录随时查看" text="保存你的推荐结果与筛选偏好，方便下次快速查看" />
        </div>
      </div>

      <aside className="login-card">
        <h2>欢迎登录</h2>
        <p>登录后可查看历史记录与个性化推荐</p>

        <form onSubmit={handleLogin}>
          <label className="input-row">
            <span className="input-icon user" />
            <input
              aria-label="用户名"
              autoComplete="username"
              maxLength={16}
              onChange={(event) => setLoginUsername(event.target.value)}
              placeholder="用户名"
              value={loginUsername}
            />
          </label>
          <label className="input-row">
            <span className="input-icon lock" />
            <input
              aria-label="密码"
              autoComplete="current-password"
              onChange={(event) => setLoginPassword(event.target.value)}
              placeholder="密码"
              type={passwordVisible ? "text" : "password"}
              value={loginPassword}
            />
            <button
              aria-label={passwordVisible ? "隐藏密码" : "显示密码"}
              className={`password-toggle ${passwordVisible ? "visible" : ""}`}
              onClick={() => setPasswordVisible((value) => !value)}
              type="button"
            >
              <span className="input-icon eye" />
            </button>
          </label>

          <div className="login-options">
            <label>
              <input
                checked={rememberMe}
                onChange={(event) => setRememberMe(event.target.checked)}
                type="checkbox"
              />
              记住我
            </label>
            <button type="button" onClick={() => { setPasswordChangeNotice(""); setChangePasswordOpen(true); }}>修改密码</button>
          </div>

          {loginMessage && <div className="auth-message error">{loginMessage}</div>}
          {passwordChangeNotice && <div className="auth-message" role="status">{passwordChangeNotice}</div>}

          <button className="primary-action" type="submit">
            登 录
          </button>
          <button className="outline-action" onClick={() => setRegisterOpen(true)} type="button">
            注册新账号
          </button>
        </form>

        <div className="role-switch">
          <button className="active" type="button">
            普通用户
          </button>
          <i />
          <button onClick={fillAdminAccount} type="button">
            管理员入口
          </button>
        </div>

        <div className="warm-tip">
          <span className="tip-icon" />
          首次使用可注册账号，开启智能租房之旅
        </div>
      </aside>

      <div className="home-cards">
        <InfoCard tone="orange" title="数据驱动推荐" text="整合交通、租金、配套等多源数据，为你提供科学租房决策参考。" />
        <InfoCard tone="green" title="全面片区信息" text="覆盖南京主城及热门板块，生活、交通、教育一目了然。" />
        <InfoCard tone="purple" title="隐私安全保障" text="严格保护你的个人信息，安心使用，放心推荐。" />
      </div>

      <footer className="page-footer">
        <span>关于我们</span>
        <i />
        <span>隐私政策</span>
        <i />
        <span>服务协议</span>
        <i />
        <span>联系我们</span>
      </footer>

      {registerOpen && <RegisterDialog onClose={() => setRegisterOpen(false)} />}
      {changePasswordOpen && (
        <ChangePasswordDialog
          initialUsername={loginUsername}
          onClose={() => setChangePasswordOpen(false)}
          onSuccess={(username) => {
            setChangePasswordOpen(false);
            setLoginUsername(username);
            setLoginPassword("");
            setLoginMessage("");
            setPasswordChangeNotice("密码已修改，请用新密码登录");
          }}
        />
      )}
    </section>
  );
}

function ChangePasswordDialog({ initialUsername, onClose, onSuccess }: {
  initialUsername: string;
  onClose: () => void;
  onSuccess: (username: string) => void;
}) {
  const [username, setUsername] = useState(initialUsername);
  const [currentPassword, setCurrentPassword] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [message, setMessage] = useState("");
  const [isSubmitting, setIsSubmitting] = useState(false);

  const handleSubmit = async (event: FormEvent) => {
    event.preventDefault();
    setMessage("");
    const trimmedUsername = username.trim();
    if (!trimmedUsername || !currentPassword || !newPassword || !confirmPassword) {
      setMessage("请填写全部信息");
      return;
    }
    if (newPassword.length < 8) {
      setMessage("新密码至少需要8位");
      return;
    }
    if (newPassword !== confirmPassword) {
      setMessage("两次输入的新密码不一致");
      return;
    }
    setIsSubmitting(true);
    try {
      await changePassword(trimmedUsername, currentPassword, newPassword, confirmPassword);
      onSuccess(trimmedUsername);
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "密码修改失败，请稍后重试");
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <div className="modal-backdrop" role="dialog" aria-modal="true" aria-label="修改密码">
      <form className="register-dialog" onSubmit={handleSubmit}>
        <div className="dialog-title-row">
          <div><h2>修改密码</h2><p>请先验证当前密码，以保护你的账号</p></div>
          <button className="dialog-close" onClick={onClose} type="button" aria-label="关闭修改密码界面">×</button>
        </div>
        <label className="dialog-field">
          <span>用户名</span>
          <input autoComplete="username" autoFocus maxLength={16} onChange={(event) => setUsername(event.target.value)} value={username} />
        </label>
        <label className="dialog-field">
          <span>当前密码</span>
          <input autoComplete="current-password" onChange={(event) => setCurrentPassword(event.target.value)} type="password" value={currentPassword} />
        </label>
        <label className="dialog-field">
          <span>新密码</span>
          <input autoComplete="new-password" minLength={8} onChange={(event) => setNewPassword(event.target.value)} type="password" value={newPassword} />
        </label>
        <label className="dialog-field">
          <span>确认密码</span>
          <input autoComplete="new-password" onChange={(event) => setConfirmPassword(event.target.value)} type="password" value={confirmPassword} />
        </label>
        {message && <div className="auth-message error" role="alert">{message}</div>}
        <button className="register-submit" disabled={isSubmitting} type="submit">
          {isSubmitting ? "修改中..." : "确认修改"}
        </button>
      </form>
    </div>
  );
}

function RegisterDialog({ onClose }: { onClose: () => void }) {
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [message, setMessage] = useState("");
  const [isSubmitting, setIsSubmitting] = useState(false);

  const handleRegister = async (event: FormEvent) => {
    event.preventDefault();
    setMessage("");

    const trimmedUsername = username.trim();
    if (!trimmedUsername) {
      setMessage("请输入用户名");
      return;
    }
    if (trimmedUsername.length > 16) {
      setMessage("用户名长度不得超过16位数字/字母/字符组合");
      return;
    }
    if (!password) {
      setMessage("请输入密码");
      return;
    }
    if (password !== confirmPassword) {
      setMessage("两次输入的密码不一致");
      return;
    }

    setIsSubmitting(true);
    try {
      await registerUser(trimmedUsername, password);
      onClose();
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "注册失败，请稍后重试");
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <div className="modal-backdrop" role="dialog" aria-modal="true" aria-label="用户注册">
      <form className="register-dialog" onSubmit={handleRegister}>
        <div className="dialog-title-row">
          <div>
            <h2>用户注册</h2>
            <p>注册后即可使用普通用户登录功能</p>
          </div>
          <button className="dialog-close" onClick={onClose} type="button" aria-label="关闭注册界面">
            ×
          </button>
        </div>

        <label className="dialog-field">
          <span>设置用户名</span>
          <input
            autoFocus
            maxLength={16}
            onChange={(event) => setUsername(event.target.value)}
            placeholder="不超过16位数字/字母/字符组合"
            value={username}
          />
        </label>
        <p className="field-help">用户名长度不得超过16位数字/字母/字符组合。</p>

        <label className="dialog-field">
          <span>设置密码</span>
          <input
            autoComplete="new-password"
            onChange={(event) => setPassword(event.target.value)}
            placeholder="请输入密码"
            type="password"
            value={password}
          />
        </label>

        <label className="dialog-field">
          <span>确认密码</span>
          <input
            autoComplete="new-password"
            onChange={(event) => setConfirmPassword(event.target.value)}
            placeholder="请再次输入密码"
            type="password"
            value={confirmPassword}
          />
        </label>

        {message && <div className="auth-message error">{message}</div>}

        <button className="register-submit" disabled={isSubmitting} type="submit">
          {isSubmitting ? "注册中..." : "注册"}
        </button>
      </form>
    </div>
  );
}

function Benefit({ icon, title, text }: { icon: string; title: string; text: string }) {
  return (
    <article className="benefit">
      <span className={`round-icon ${icon}`} />
      <div>
        <h3>{title}</h3>
        <p>{text}</p>
      </div>
    </article>
  );
}

function InfoCard({ tone, title, text }: { tone: string; title: string; text: string }) {
  return (
    <article className="home-card">
      <span className={`big-icon ${tone}`} />
      <div>
        <h3>{title}</h3>
        <p>{text}</p>
      </div>
    </article>
  );
}
