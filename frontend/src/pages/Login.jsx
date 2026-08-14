import { useEffect, useRef, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { useAuth } from "../contexts/AuthContext";
import FormInput from "../components/FormInput";
import ErrorAlert from "../components/ErrorAlert";

export default function Login() {
  const { login } = useAuth();
  const navigate = useNavigate();
  const [form, setForm] = useState({ email: "", password: "" });
  const [error, setError] = useState(null);
  const [submitting, setSubmitting] = useState(false);
  const [lampState, setLampState] = useState("off");
  const pullStart = useRef(null);
  const suppressClick = useRef(false);
  const lampTimer = useRef(null);
  const navigationTimer = useRef(null);

  useEffect(() => () => {
    window.clearTimeout(lampTimer.current);
    window.clearTimeout(navigationTimer.current);
  }, []);

  const toggleLamp = () => {
    if (submitting || lampState === "turning-on" || lampState === "turning-off") return;
    const turningOn = lampState === "off";
    setLampState(turningOn ? "turning-on" : "turning-off");
    window.clearTimeout(lampTimer.current);
    lampTimer.current = window.setTimeout(() => setLampState(turningOn ? "on" : "off"), 520);
  };

  const onPullStart = (event) => {
    pullStart.current = event.clientY;
    event.currentTarget.setPointerCapture?.(event.pointerId);
  };

  const onPullMove = (event) => {
    if (pullStart.current !== null && event.clientY - pullStart.current > 18) {
      suppressClick.current = true;
      toggleLamp();
      pullStart.current = null;
    }
  };

  const onPullEnd = () => {
    pullStart.current = null;
    window.setTimeout(() => { suppressClick.current = false; }, 0);
  };

  const onPullClick = () => {
    if (suppressClick.current) {
      suppressClick.current = false;
      return;
    }
    toggleLamp();
  };

  const onSubmit = async (e) => {
    e.preventDefault();
    setError(null);
    setSubmitting(true);
    try {
      await login(form.email, form.password);
      navigationTimer.current = window.setTimeout(() => navigate("/dashboard"), 560);
    } catch (err) {
      setError(err);
      setSubmitting(false);
    }
  };

  return (
    <main className={"lamp-login-page lamp-" + lampState}>
      <div className="lamp-ambient" aria-hidden="true" />
      <div className="lamp-fixture" aria-hidden="true">
        <div className="lamp-shade"><span /></div>
        <div className="lamp-bulb" />
      </div>

      <button
        type="button"
        className="lamp-pull"
        aria-label={lampState === "on" || lampState === "turning-off" ? "Turn lamp off" : "Turn lamp on"}
        aria-pressed={lampState === "on" || lampState === "turning-on"}
        aria-disabled={submitting || lampState === "turning-on" || lampState === "turning-off"}
        onClick={onPullClick}
        onPointerDown={onPullStart}
        onPointerMove={onPullMove}
        onPointerUp={onPullEnd}
        onPointerCancel={onPullEnd}
        disabled={submitting}
      >
        <span className="lamp-cord" aria-hidden="true" />
        <span className="lamp-pull-handle" aria-hidden="true" />
      </button>

      <section className="lamp-login-content">
        <div className="lamp-branding">
          <span className="lamp-eyebrow">Agentic intelligence for every review</span>
          <h1>Sentiment Analysis<br /><em>Management System</em></h1>
          <p>Turn customer voice into a clearer next move.</p>
        </div>

        <form className="lamp-login-panel" onSubmit={onSubmit} aria-label="Log in">
          <div className="lamp-panel-heading">
            <span className="lamp-panel-kicker">Welcome back</span>
            <h2>Log in to your workspace</h2>
          </div>
          <ErrorAlert error={error} onDismiss={() => setError(null)} />
          <FormInput
            label="Email"
            type="email"
            required
            value={form.email}
            onChange={(e) => setForm({ ...form, email: e.target.value })}
          />
          <FormInput
            label="Password"
            type="password"
            required
            value={form.password}
            onChange={(e) => setForm({ ...form, password: e.target.value })}
          />
          <button className="lamp-submit" type="submit" disabled={submitting}>
            <span>{submitting ? "Logging in..." : "Continue"}</span>
            <span aria-hidden="true">→</span>
          </button>
          <p className="lamp-register">
            No account? <Link to="/register">Register your organisation</Link>
          </p>
        </form>
      </section>
    </main>
  );
}
