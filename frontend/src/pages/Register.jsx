import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { useAuth } from "../contexts/AuthContext";
import FormInput from "../components/FormInput";
import ErrorAlert from "../components/ErrorAlert";

export default function Register() {
  const { register } = useAuth();
  const navigate = useNavigate();
  const [form, setForm] = useState({
    organisationName: "", name: "", email: "", password: "",
  });
  const [error, setError] = useState(null);
  const [submitting, setSubmitting] = useState(false);

  const onSubmit = async (e) => {
    e.preventDefault();
    setError(null);
    setSubmitting(true);
    try {
      await register(form);
      navigate("/dashboard");
    } catch (err) {
      if (err?.response?.data?.error?.code === "EMAIL_ALREADY_REGISTERED") {
        setError({ message: "An account with this email already exists. Log in instead." });
      } else {
        setError(err);
      }
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <form className="auth-register-panel" onSubmit={onSubmit} aria-label="Register your organisation">
      <h4 className="mb-3">Register your organisation</h4>
      <ErrorAlert error={error} onDismiss={() => setError(null)} />
      <FormInput
        label="Organisation name"
        required
        value={form.organisationName}
        onChange={(e) => setForm({ ...form, organisationName: e.target.value })}
      />
      <FormInput
        label="Your name"
        required
        autoComplete="name"
        value={form.name}
        onChange={(e) => setForm({ ...form, name: e.target.value })}
      />
      <FormInput
        label="Email"
        type="email"
        autoComplete="email"
        required
        value={form.email}
        onChange={(e) => setForm({ ...form, email: e.target.value })}
      />
      <FormInput
        label="Password"
        type="password"
        autoComplete="new-password"
        required
        minLength={10}
        value={form.password}
        onChange={(e) => setForm({ ...form, password: e.target.value })}
      />
      <button className="btn btn-primary w-100" type="submit" disabled={submitting}>
        {submitting ? "Creating..." : "Create organisation"}
      </button>
      <p className="auth-register-link mt-3 mb-0 text-center">
        Already have an account? <Link to="/login">Log in</Link>
      </p>
    </form>
  );
}
