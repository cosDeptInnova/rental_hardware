import React, { useMemo, useState } from "react";
import { motion } from "framer-motion";
import {
  Activity,
  BarChart3,
  CheckCircle2,
  Clock3,
  Copy,
  Database,
  KeyRound,
  Rocket,
  Sparkles,
  Terminal,
  Timer,
} from "lucide-react";

import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Slider } from "@/components/ui/slider";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";

const modelCatalog = [
  { id: "mistral-7b-instruct", label: "Mistral 7B Instruct", minVram: 8, services: ["inference"] },
  { id: "gpt-oss-20b-gguf", label: "GPT-OSS 20B GGUF", minVram: 14, services: ["inference"] },
  { id: "nomic-embed-text", label: "Nomic Embed Text", minVram: 4, services: ["embeddings"] },
  { id: "bge-large-es", label: "BGE Large ES", minVram: 6, services: ["embeddings"] },
];

const serviceMeta = {
  inference: { label: "Inferencia", icon: Sparkles, endpoint: "/inference" },
  embeddings: { label: "Embeddings", icon: Database, endpoint: "/embeddings" },
};

function slugify(v) {
  return (
    v
      .toLowerCase()
      .normalize("NFD")
      .replace(/[\u0300-\u036f]/g, "")
      .replace(/[^a-z0-9]+/g, "-")
      .replace(/^-+|-+$/g, "") || "tenant-demo"
  );
}

async function api(url, options = {}) {
  const response = await fetch(url, {
    ...options,
    headers: {
      "Content-Type": "application/json",
      ...(options.headers || {}),
    },
  });

  const body = await response.json().catch(() => ({}));
  if (!response.ok) {
    const error = body?.detail || body?.error || `HTTP ${response.status}`;
    throw new Error(typeof error === "string" ? error : JSON.stringify(error));
  }

  return body;
}

export default function GpuRentingFrontend() {
  const [apiBasePath, setApiBasePath] = useState("/broker-api");
  const [adminToken, setAdminToken] = useState("change-me");
  const [tenantName, setTenantName] = useState("Cliente Demo");
  const [service, setService] = useState("inference");
  const [model, setModel] = useState("mistral-7b-instruct");
  const [vram, setVram] = useState([12]);

  const [apiKey, setApiKey] = useState("");
  const [tenantId, setTenantId] = useState("");
  const [requestJson, setRequestJson] = useState('{"messages":[{"role":"user","content":"Resume este documento"}],"temperature":0.2}');

  const [deployLoading, setDeployLoading] = useState(false);
  const [invokeLoading, setInvokeLoading] = useState(false);
  const [analyticsLoading, setAnalyticsLoading] = useState(false);

  const [lastResponse, setLastResponse] = useState(null);
  const [analytics, setAnalytics] = useState(null);
  const [error, setError] = useState("");

  const compatibleModels = useMemo(
    () => modelCatalog.filter((m) => m.services.includes(service)),
    [service]
  );

  const selectedModel = useMemo(
    () => compatibleModels.find((m) => m.id === model) || compatibleModels[0],
    [compatibleModels, model]
  );

  const backendEndpoint = useMemo(() => `${apiBasePath}${serviceMeta[service].endpoint}`, [apiBasePath, service]);

  const canDeploy = vram[0] >= (selectedModel?.minVram || 0);

  const provisionTenant = async () => {
    setError("");
    setDeployLoading(true);
    try {
      const tenant = await api(`${apiBasePath}/admin/tenants`, {
        method: "POST",
        headers: { "X-Admin-Token": adminToken },
        body: JSON.stringify({ name: tenantName || slugify(tenantName) }),
      });

      const reservation = {
        tenant_id: tenant.tenant_id,
        reserved_vram_mb: vram[0] * 1024,
        max_concurrency: 4,
        priority: 80,
        allowed_services: ["inference", "embeddings"],
        preemptive: true,
        enabled: true,
      };

      await api(`${apiBasePath}/admin/reservations`, {
        method: "POST",
        headers: { "X-Admin-Token": adminToken },
        body: JSON.stringify(reservation),
      });

      setApiKey(tenant.api_key);
      setTenantId(tenant.tenant_id);
    } catch (e) {
      setError(e.message);
    } finally {
      setDeployLoading(false);
    }
  };

  const invokeService = async () => {
    setError("");
    setInvokeLoading(true);
    try {
      const payload = JSON.parse(requestJson);
      const body = await api(`${apiBasePath}${serviceMeta[service].endpoint}`, {
        method: "POST",
        headers: { "X-API-Key": apiKey },
        body: JSON.stringify({
          model: selectedModel.id,
          requested_vram_mb: vram[0] * 1024,
          priority: 50,
          payload,
        }),
      });
      setLastResponse(body);
      await loadAnalytics();
    } catch (e) {
      setError(e.message);
    } finally {
      setInvokeLoading(false);
    }
  };

  const loadAnalytics = async () => {
    if (!apiKey) return;
    setAnalyticsLoading(true);
    try {
      const body = await api(`${apiBasePath}/analytics/summary`, {
        headers: { "X-API-Key": apiKey },
      });
      setAnalytics(body);
    } catch (e) {
      setError(e.message);
    } finally {
      setAnalyticsLoading(false);
    }
  };

  const successRate = useMemo(() => {
    if (!analytics || analytics.requests_total === 0) return 0;
    return Math.round((analytics.success_total / analytics.requests_total) * 100);
  }, [analytics]);

  const copy = async (text) => {
    try {
      await navigator.clipboard.writeText(text);
    } catch {
      // ignore
    }
  };

  return (
    <div className="min-h-screen bg-slate-50">
      <div className="mx-auto max-w-7xl px-4 py-8 md:px-8">
        <motion.div initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} className="mb-8">
          <Card className="rounded-3xl border-0 shadow-lg">
            <CardHeader>
              <div className="mb-2 flex items-center gap-2">
                <Badge className="rounded-full">GPU Renting</Badge>
                <Badge variant="secondary" className="rounded-full">llama.cpp Managed</Badge>
              </div>
              <CardTitle className="text-3xl">Portal conectado al backend</CardTitle>
              <CardDescription>
                Provisiona tenant + reserva, ejecuta inferencia/embeddings y visualiza analytics de tokens, latencia y estados en tiempo real.
              </CardDescription>
            </CardHeader>
          </Card>
        </motion.div>

        <div className="grid gap-6 xl:grid-cols-[1.35fr_1fr]">
          <Card className="rounded-3xl border-0 shadow-lg">
            <CardHeader>
              <CardTitle>Configuración y conexión</CardTitle>
              <CardDescription>Backend FastAPI + endpoints de servicio y analytics.</CardDescription>
            </CardHeader>
            <CardContent className="space-y-6">
              <div className="grid gap-4 md:grid-cols-2">
                <div className="space-y-2">
                  <Label>API path vía Nginx</Label>
                  <Input value={apiBasePath} onChange={(e) => setApiBasePath(e.target.value)} className="rounded-2xl" />
                </div>
                <div className="space-y-2">
                  <Label>Admin token</Label>
                  <Input value={adminToken} onChange={(e) => setAdminToken(e.target.value)} className="rounded-2xl" />
                </div>
              </div>

              <Tabs value={service} onValueChange={(next) => {
                setService(next);
                const first = modelCatalog.find((m) => m.services.includes(next));
                if (first) {
                  setModel(first.id);
                  setVram([Math.max(vram[0], first.minVram)]);
                }
              }}>
                <TabsList className="grid w-full grid-cols-2 rounded-2xl">
                  <TabsTrigger value="inference">Inferencia</TabsTrigger>
                  <TabsTrigger value="embeddings">Embeddings</TabsTrigger>
                </TabsList>
                <TabsContent value="inference" className="mt-4" />
                <TabsContent value="embeddings" className="mt-4" />
              </Tabs>

              <div className="grid gap-4 md:grid-cols-2">
                <div className="space-y-2">
                  <Label>Tenant</Label>
                  <Input value={tenantName} onChange={(e) => setTenantName(e.target.value)} className="rounded-2xl" />
                </div>
                <div className="space-y-2">
                  <Label>Modelo</Label>
                  <Select value={model} onValueChange={setModel}>
                    <SelectTrigger className="rounded-2xl"><SelectValue /></SelectTrigger>
                    <SelectContent>
                      {compatibleModels.map((m) => <SelectItem key={m.id} value={m.id}>{m.label}</SelectItem>)}
                    </SelectContent>
                  </Select>
                </div>
              </div>

              <div className="rounded-2xl border bg-slate-50 p-5">
                <div className="mb-3 flex items-center justify-between">
                  <div>
                    <p className="font-medium">VRAM reservada</p>
                    <p className="text-sm text-slate-600">Controla capacidad a reservar para el tenant.</p>
                  </div>
                  <Badge variant="secondary">{vram[0]} GB</Badge>
                </div>
                <Slider min={4} max={48} step={1} value={vram} onValueChange={setVram} />
              </div>

              <div className="space-y-2">
                <Label>Payload JSON para llama.cpp server</Label>
                <textarea
                  value={requestJson}
                  onChange={(e) => setRequestJson(e.target.value)}
                  rows={7}
                  className="w-full rounded-2xl border bg-white p-3 font-mono text-xs"
                />
              </div>

              <div className="flex flex-wrap gap-3">
                <Button className="rounded-2xl" disabled={!canDeploy || deployLoading} onClick={provisionTenant}>
                  <Rocket className="mr-2 h-4 w-4" />
                  {deployLoading ? "Provisionando..." : "Crear tenant + reserva"}
                </Button>
                <Button variant="secondary" className="rounded-2xl" disabled={!apiKey || invokeLoading} onClick={invokeService}>
                  <Terminal className="mr-2 h-4 w-4" />
                  {invokeLoading ? "Invocando..." : `Probar ${serviceMeta[service].label}`}
                </Button>
                <Button variant="outline" className="rounded-2xl" disabled={!apiKey || analyticsLoading} onClick={loadAnalytics}>
                  <Activity className="mr-2 h-4 w-4" />
                  Actualizar analytics
                </Button>
              </div>

              {!canDeploy && (
                <Alert>
                  <AlertTitle>VRAM insuficiente</AlertTitle>
                  <AlertDescription>El modelo requiere al menos {selectedModel.minVram} GB.</AlertDescription>
                </Alert>
              )}

              {error && (
                <Alert className="border-rose-300 bg-rose-50 text-rose-900">
                  <AlertTitle>Error</AlertTitle>
                  <AlertDescription>{error}</AlertDescription>
                </Alert>
              )}
            </CardContent>
          </Card>

          <div className="space-y-6">
            <Card className="rounded-3xl border-0 shadow-lg">
              <CardHeader>
                <CardTitle>Conexión activa</CardTitle>
                <CardDescription>Credenciales y endpoint conectados al backend real.</CardDescription>
              </CardHeader>
              <CardContent className="space-y-3 text-sm">
                <div className="rounded-xl border bg-white p-3">
                  <p className="text-slate-500">Tenant ID</p>
                  <p className="break-all font-medium">{tenantId || "-"}</p>
                </div>
                <div className="rounded-xl border bg-white p-3">
                  <div className="mb-2 flex items-center justify-between">
                    <p className="text-slate-500">API Key</p>
                    <Button size="sm" variant="outline" onClick={() => copy(apiKey)} className="rounded-xl" disabled={!apiKey}>
                      <Copy className="mr-2 h-3 w-3" /> Copiar
                    </Button>
                  </div>
                  <p className="break-all font-mono text-xs">{apiKey || "-"}</p>
                </div>
                <div className="rounded-xl border bg-white p-3">
                  <p className="text-slate-500">Endpoint</p>
                  <p className="break-all font-medium">{backendEndpoint}</p>
                </div>
              </CardContent>
            </Card>

            <Card className="rounded-3xl border-0 shadow-lg">
              <CardHeader>
                <div className="flex items-center justify-between">
                  <div>
                    <CardTitle>Analytics</CardTitle>
                    <CardDescription>Tokens, llamadas, estados y latencia.</CardDescription>
                  </div>
                  <BarChart3 className="h-5 w-5 text-slate-500" />
                </div>
              </CardHeader>
              <CardContent className="space-y-4">
                <div className="grid grid-cols-2 gap-3">
                  <div className="rounded-2xl bg-slate-100 p-3">
                    <p className="text-xs text-slate-500">Llamadas</p>
                    <p className="text-2xl font-semibold">{analytics?.requests_total ?? 0}</p>
                  </div>
                  <div className="rounded-2xl bg-slate-100 p-3">
                    <p className="text-xs text-slate-500">Tokens totales</p>
                    <p className="text-2xl font-semibold">{analytics?.total_tokens_total ?? 0}</p>
                  </div>
                  <div className="rounded-2xl bg-slate-100 p-3">
                    <p className="text-xs text-slate-500">Latencia media</p>
                    <p className="text-2xl font-semibold">{Math.round(analytics?.avg_latency_ms ?? 0)} ms</p>
                  </div>
                  <div className="rounded-2xl bg-slate-100 p-3">
                    <p className="text-xs text-slate-500">Éxito</p>
                    <p className="text-2xl font-semibold">{successRate}%</p>
                  </div>
                </div>

                <div className="space-y-2 rounded-2xl border bg-white p-4">
                  <div className="flex items-center justify-between text-sm">
                    <span className="inline-flex items-center gap-2"><CheckCircle2 className="h-4 w-4 text-emerald-600" />Correctas</span>
                    <span>{analytics?.success_total ?? 0}</span>
                  </div>
                  <div className="h-2 overflow-hidden rounded-full bg-slate-200">
                    <div className="h-full bg-emerald-500" style={{ width: `${successRate}%` }} />
                  </div>
                  <div className="flex items-center justify-between text-sm text-slate-600">
                    <span className="inline-flex items-center gap-2"><Clock3 className="h-4 w-4" />Con error</span>
                    <span>{analytics?.failed_total ?? 0}</span>
                  </div>
                </div>

                <div className="rounded-2xl border bg-white p-4">
                  <p className="mb-2 text-sm font-medium">Desglose por servicio</p>
                  <div className="space-y-2 text-sm">
                    {(analytics?.by_service || []).map((row) => (
                      <div key={row.service_type} className="rounded-xl bg-slate-50 p-3">
                        <div className="mb-1 flex items-center justify-between">
                          <span className="font-medium capitalize">{row.service_type}</span>
                          <Badge variant="secondary">{row.requests} req</Badge>
                        </div>
                        <div className="grid grid-cols-2 gap-1 text-xs text-slate-600">
                          <span>Input: {row.request_tokens}</span>
                          <span>Output: {row.response_tokens}</span>
                          <span>Total: {row.total_tokens}</span>
                          <span><Timer className="mr-1 inline h-3 w-3" />{Math.round(row.avg_latency_ms)} ms</span>
                        </div>
                      </div>
                    ))}
                    {!analytics?.by_service?.length && <p className="text-slate-500">Sin datos aún.</p>}
                  </div>
                </div>
              </CardContent>
            </Card>
          </div>
        </div>

        {lastResponse && (
          <motion.div initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} className="mt-6">
            <Card className="rounded-3xl border-0 shadow-lg">
              <CardHeader>
                <CardTitle>Última respuesta del backend</CardTitle>
                <CardDescription>Respuesta real del endpoint gestionado por llama.cpp / fallback backend.</CardDescription>
              </CardHeader>
              <CardContent>
                <pre className="overflow-x-auto rounded-2xl bg-slate-900 p-4 text-xs text-slate-100">
                  {JSON.stringify(lastResponse, null, 2)}
                </pre>
              </CardContent>
            </Card>
          </motion.div>
        )}

        <div className="mt-6 rounded-2xl border border-dashed bg-white p-4 text-sm text-slate-600">
          <p className="inline-flex items-center gap-2 font-medium"><KeyRound className="h-4 w-4" />Flujo recomendado</p>
          <ol className="mt-2 list-decimal space-y-1 pl-5">
            <li>Configurar backend URL y token admin.</li>
            <li>Crear tenant + reserva (genera API key).</li>
            <li>Probar inferencia/embeddings con payload JSON.</li>
            <li>Abrir analytics y validar tokens, llamadas y estados.</li>
          </ol>
        </div>
      </div>
    </div>
  );
}
