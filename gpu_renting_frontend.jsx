import React, { useMemo, useState } from "react";
import { motion } from "framer-motion";
import { Cpu, Database, Globe, KeyRound, ServerCog, ShieldCheck, Sparkles, Zap, CheckCircle2, Copy, Rocket, Gauge, Layers3 } from "lucide-react";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Badge } from "@/components/ui/badge";
import { Slider } from "@/components/ui/slider";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Switch } from "@/components/ui/switch";
import { Separator } from "@/components/ui/separator";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";

const models = [
  {
    id: "gpt-oss-20b-gguf",
    name: "GPT-OSS 20B GGUF",
    type: "Inference",
    minVram: 12,
    recommendedVram: 20,
    description: "Modelo conversacional servido sobre llama.cpp para inferencia gestionada.",
    services: ["inference"],
  },
  {
    id: "nomic-embed-text",
    name: "Nomic Embed Text",
    type: "Embeddings",
    minVram: 4,
    recommendedVram: 8,
    description: "Servicio de embeddings para indexación, búsqueda semántica y RAG.",
    services: ["embeddings", "rag"],
  },
  {
    id: "bge-large-es",
    name: "BGE Large ES",
    type: "Embeddings / Rerank",
    minVram: 6,
    recommendedVram: 10,
    description: "Embeddings de alta calidad para recuperación y pipelines RAG empresariales.",
    services: ["embeddings", "rag"],
  },
  {
    id: "mistral-7b-instruct",
    name: "Mistral 7B Instruct",
    type: "Inference",
    minVram: 8,
    recommendedVram: 12,
    description: "Modelo ligero para asistentes, clasificación y generación de texto.",
    services: ["inference", "rag"],
  },
];

const serviceInfo = {
  inference: {
    label: "Inferencia",
    icon: Sparkles,
    endpoint: "/v1/chat/completions",
    color: "Servicio gestionado",
  },
  embeddings: {
    label: "Embeddings",
    icon: Database,
    endpoint: "/v1/embeddings",
    color: "Vectorización",
  },
  rag: {
    label: "RAG",
    icon: Layers3,
    endpoint: "/v1/rag/query",
    color: "Recuperación + generación",
  },
};

function makeSlug(input) {
  return input
    .toLowerCase()
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "")
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "") || "tenant-demo";
}

function estimateMonthlyPrice({ vram, service, dedicated }) {
  const base = dedicated ? 380 : 210;
  const serviceFactor = service === "inference" ? 1.25 : service === "rag" ? 1.4 : 1.0;
  const vramFactor = vram * 24;
  return Math.round((base + vramFactor) * serviceFactor);
}

function estimateSetupPrice({ service, auth, privateNetwork }) {
  let total = 450;
  if (service === "rag") total += 200;
  if (auth) total += 120;
  if (privateNetwork) total += 180;
  return total;
}

export default function GpuRentingFrontend() {
  const [tenantName, setTenantName] = useState("Cliente Demo");
  const [subdomain, setSubdomain] = useState("cliente-demo");
  const [service, setService] = useState("inference");
  const [modelId, setModelId] = useState("gpt-oss-20b-gguf");
  const [vram, setVram] = useState([20]);
  const [region, setRegion] = useState("eu-west");
  const [scaling, setScaling] = useState("reserved");
  const [dedicatedWindow, setDedicatedWindow] = useState(true);
  const [privateNetwork, setPrivateNetwork] = useState(false);
  const [apiKeyAuth, setApiKeyAuth] = useState(true);
  const [generated, setGenerated] = useState(false);

  const selectedModel = useMemo(() => models.find((m) => m.id === modelId) ?? models[0], [modelId]);

  const compatibleModels = useMemo(
    () => models.filter((m) => m.services.includes(service)),
    [service]
  );

  const normalizedSubdomain = useMemo(() => makeSlug(subdomain || tenantName), [subdomain, tenantName]);

  const endpointBase = useMemo(() => {
    const domain = privateNetwork
      ? `https://${normalizedSubdomain}.priv.gpu-service.local`
      : `https://${normalizedSubdomain}.gpu-service.example.com`;
    return `${domain}${serviceInfo[service].endpoint}`;
  }, [normalizedSubdomain, privateNetwork, service]);

  const monthlyPrice = useMemo(
    () => estimateMonthlyPrice({ vram: vram[0], service, dedicated: dedicatedWindow }),
    [vram, service, dedicatedWindow]
  );

  const setupPrice = useMemo(
    () => estimateSetupPrice({ service, auth: apiKeyAuth, privateNetwork }),
    [service, apiKeyAuth, privateNetwork]
  );

  const serviceMeta = serviceInfo[service];
  const ServiceIcon = serviceMeta.icon;

  const canDeploy = vram[0] >= selectedModel.minVram;

  const sampleCurl = useMemo(() => {
    if (service === "inference") {
      return `curl -X POST '${endpointBase}' \\
  -H 'Authorization: Bearer sk_live_xxx' \\
  -H 'Content-Type: application/json' \\
  -d '{
    "model": "${selectedModel.id}",
    "messages": [{"role": "user", "content": "Hola, resume este documento"}],
    "temperature": 0.2
  }'`;
    }

    if (service === "embeddings") {
      return `curl -X POST '${endpointBase}' \\
  -H 'Authorization: Bearer sk_live_xxx' \\
  -H 'Content-Type: application/json' \\
  -d '{
    "model": "${selectedModel.id}",
    "input": ["texto para vectorizar"]
  }'`;
    }

    return `curl -X POST '${endpointBase}' \\
  -H 'Authorization: Bearer sk_live_xxx' \\
  -H 'Content-Type: application/json' \\
  -d '{
    "model": "${selectedModel.id}",
    "query": "¿Qué SLA tiene el servicio?",
    "top_k": 5,
    "namespace": "cliente-demo"
  }'`;
  }, [endpointBase, selectedModel.id, service]);

  const handleServiceChange = (nextService) => {
    setService(nextService);
    const firstCompatible = models.find((m) => m.services.includes(nextService));
    if (firstCompatible) {
      setModelId(firstCompatible.id);
      setVram([Math.max(vram[0], firstCompatible.recommendedVram)]);
    }
    setGenerated(false);
  };

  const handleModelChange = (nextModelId) => {
    setModelId(nextModelId);
    const m = models.find((item) => item.id === nextModelId);
    if (m) {
      setVram([Math.max(vram[0], m.minVram)]);
    }
    setGenerated(false);
  };

  const deploy = () => {
    setGenerated(true);
  };

  const copyText = async (text) => {
    try {
      await navigator.clipboard.writeText(text);
    } catch {
      // noop for preview environments
    }
  };

  return (
    <div className="min-h-screen bg-slate-50">
      <div className="mx-auto max-w-7xl px-4 py-8 md:px-8 lg:px-10">
        <motion.div
          initial={{ opacity: 0, y: 10 }}
          animate={{ opacity: 1, y: 0 }}
          className="mb-8 grid gap-4 lg:grid-cols-[1.4fr_0.9fr]"
        >
          <Card className="rounded-3xl border-0 shadow-lg">
            <CardHeader className="pb-4">
              <div className="mb-4 flex items-center gap-2">
                <Badge className="rounded-full">GPU Renting</Badge>
                <Badge variant="secondary" className="rounded-full">L40S Managed Service</Badge>
              </div>
              <CardTitle className="text-3xl font-semibold tracking-tight">
                Portal de contratación y despliegue de servicios GPU
              </CardTitle>
              <CardDescription className="max-w-2xl text-base leading-7">
                Configura VRAM reservada, elige modelo, selecciona el tipo de servicio y genera un endpoint de inferencia listo para integrarse con tu aplicación.
              </CardDescription>
            </CardHeader>
            <CardContent>
              <div className="grid gap-4 md:grid-cols-3">
                <div className="rounded-2xl bg-slate-100 p-4">
                  <div className="mb-2 flex items-center gap-2 text-sm font-medium text-slate-700">
                    <ShieldCheck className="h-4 w-4" />
                    Servicio gestionado
                  </div>
                  <p className="text-sm text-slate-600">Sin acceso a sistema operativo ni GPU directa. Consumo mediante API segura.</p>
                </div>
                <div className="rounded-2xl bg-slate-100 p-4">
                  <div className="mb-2 flex items-center gap-2 text-sm font-medium text-slate-700">
                    <Gauge className="h-4 w-4" />
                    Capacidad reservada
                  </div>
                  <p className="text-sm text-slate-600">Reserva de VRAM, control de concurrencia y priorización por tenant.</p>
                </div>
                <div className="rounded-2xl bg-slate-100 p-4">
                  <div className="mb-2 flex items-center gap-2 text-sm font-medium text-slate-700">
                    <Rocket className="h-4 w-4" />
                    Endpoint dedicado
                  </div>
                  <p className="text-sm text-slate-600">Provisionado de endpoint HTTPS con autenticación y catálogo controlado de modelos.</p>
                </div>
              </div>
            </CardContent>
          </Card>

          <Card className="rounded-3xl border-0 shadow-lg">
            <CardHeader>
              <CardTitle className="text-xl">Resumen comercial</CardTitle>
              <CardDescription>Estimación orientativa para propuesta y preventa.</CardDescription>
            </CardHeader>
            <CardContent className="space-y-5">
              <div className="rounded-2xl bg-slate-100 p-4">
                <div className="text-sm text-slate-500">Cuota mensual estimada</div>
                <div className="mt-1 text-3xl font-semibold">{monthlyPrice.toLocaleString("es-ES")} €</div>
                <div className="mt-1 text-sm text-slate-600">Incluye capacidad reservada, operación y endpoint gestionado.</div>
              </div>
              <div className="rounded-2xl bg-slate-100 p-4">
                <div className="text-sm text-slate-500">Puesta en marcha estimada</div>
                <div className="mt-1 text-2xl font-semibold">{setupPrice.toLocaleString("es-ES")} €</div>
                <div className="mt-1 text-sm text-slate-600">Configuración inicial, despliegue y validación técnica.</div>
              </div>
              <div className="grid gap-3 text-sm text-slate-600">
                <div className="flex items-center justify-between rounded-xl border bg-white px-3 py-2">
                  <span>VRAM reservada</span>
                  <span className="font-medium text-slate-900">{vram[0]} GB</span>
                </div>
                <div className="flex items-center justify-between rounded-xl border bg-white px-3 py-2">
                  <span>Servicio</span>
                  <span className="font-medium text-slate-900">{serviceMeta.label}</span>
                </div>
                <div className="flex items-center justify-between rounded-xl border bg-white px-3 py-2">
                  <span>Modelo</span>
                  <span className="font-medium text-slate-900">{selectedModel.name}</span>
                </div>
              </div>
            </CardContent>
          </Card>
        </motion.div>

        <div className="grid gap-6 xl:grid-cols-[1.3fr_0.9fr]">
          <Card className="rounded-3xl border-0 shadow-lg">
            <CardHeader>
              <CardTitle>Configurar servicio GPU</CardTitle>
              <CardDescription>Define el tenant, la capacidad y el endpoint que se va a provisionar.</CardDescription>
            </CardHeader>
            <CardContent>
              <Tabs defaultValue="service" className="w-full">
                <TabsList className="mb-6 grid w-full grid-cols-3 rounded-2xl">
                  <TabsTrigger value="service">Servicio</TabsTrigger>
                  <TabsTrigger value="capacity">Capacidad</TabsTrigger>
                  <TabsTrigger value="network">Red y seguridad</TabsTrigger>
                </TabsList>

                <TabsContent value="service" className="space-y-6">
                  <div className="grid gap-5 md:grid-cols-2">
                    <div className="space-y-2">
                      <Label>Nombre del cliente / tenant</Label>
                      <Input
                        value={tenantName}
                        onChange={(e) => {
                          setTenantName(e.target.value);
                          if (!subdomain || subdomain === makeSlug(tenantName)) {
                            setSubdomain(makeSlug(e.target.value));
                          }
                          setGenerated(false);
                        }}
                        placeholder="Ej. Cliente Demo"
                        className="rounded-2xl"
                      />
                    </div>
                    <div className="space-y-2">
                      <Label>Subdominio / namespace</Label>
                      <Input
                        value={subdomain}
                        onChange={(e) => {
                          setSubdomain(e.target.value);
                          setGenerated(false);
                        }}
                        placeholder="cliente-demo"
                        className="rounded-2xl"
                      />
                    </div>
                  </div>

                  <div className="grid gap-5 md:grid-cols-2">
                    <div className="space-y-2">
                      <Label>Tipo de servicio</Label>
                      <Select value={service} onValueChange={handleServiceChange}>
                        <SelectTrigger className="rounded-2xl">
                          <SelectValue />
                        </SelectTrigger>
                        <SelectContent>
                          <SelectItem value="inference">Inferencia</SelectItem>
                          <SelectItem value="embeddings">Embeddings</SelectItem>
                          <SelectItem value="rag">RAG</SelectItem>
                        </SelectContent>
                      </Select>
                    </div>
                    <div className="space-y-2">
                      <Label>Modelo</Label>
                      <Select value={modelId} onValueChange={handleModelChange}>
                        <SelectTrigger className="rounded-2xl">
                          <SelectValue />
                        </SelectTrigger>
                        <SelectContent>
                          {compatibleModels.map((model) => (
                            <SelectItem key={model.id} value={model.id}>
                              {model.name}
                            </SelectItem>
                          ))}
                        </SelectContent>
                      </Select>
                    </div>
                  </div>

                  <div className="rounded-2xl border bg-slate-50 p-5">
                    <div className="mb-3 flex items-center justify-between">
                      <div>
                        <div className="font-medium text-slate-900">Ficha del modelo</div>
                        <div className="text-sm text-slate-600">{selectedModel.description}</div>
                      </div>
                      <Badge variant="secondary" className="rounded-full">{selectedModel.type}</Badge>
                    </div>
                    <div className="grid gap-3 md:grid-cols-3">
                      <div className="rounded-xl bg-white p-3 text-sm">
                        <div className="text-slate-500">VRAM mínima</div>
                        <div className="mt-1 font-semibold text-slate-900">{selectedModel.minVram} GB</div>
                      </div>
                      <div className="rounded-xl bg-white p-3 text-sm">
                        <div className="text-slate-500">VRAM recomendada</div>
                        <div className="mt-1 font-semibold text-slate-900">{selectedModel.recommendedVram} GB</div>
                      </div>
                      <div className="rounded-xl bg-white p-3 text-sm">
                        <div className="text-slate-500">Endpoint</div>
                        <div className="mt-1 font-semibold text-slate-900">{serviceMeta.endpoint}</div>
                      </div>
                    </div>
                  </div>
                </TabsContent>

                <TabsContent value="capacity" className="space-y-6">
                  <div className="rounded-2xl border bg-slate-50 p-5">
                    <div className="mb-4 flex items-center justify-between">
                      <div>
                        <div className="font-medium text-slate-900">VRAM reservada</div>
                        <div className="text-sm text-slate-600">Elige la capacidad garantizada para el servicio del cliente.</div>
                      </div>
                      <div className="text-3xl font-semibold">{vram[0]} GB</div>
                    </div>
                    <Slider
                      value={vram}
                      onValueChange={(value) => {
                        setVram(value);
                        setGenerated(false);
                      }}
                      min={4}
                      max={24}
                      step={1}
                    />
                    <div className="mt-3 flex justify-between text-xs text-slate-500">
                      <span>4 GB</span>
                      <span>12 GB</span>
                      <span>20 GB</span>
                      <span>24 GB</span>
                    </div>
                  </div>

                  <div className="grid gap-5 md:grid-cols-2">
                    <div className="space-y-2">
                      <Label>Región</Label>
                      <Select value={region} onValueChange={(value) => { setRegion(value); setGenerated(false); }}>
                        <SelectTrigger className="rounded-2xl">
                          <SelectValue />
                        </SelectTrigger>
                        <SelectContent>
                          <SelectItem value="eu-west">EU West</SelectItem>
                          <SelectItem value="eu-south">EU South</SelectItem>
                          <SelectItem value="on-prem">On-premise</SelectItem>
                        </SelectContent>
                      </Select>
                    </div>
                    <div className="space-y-2">
                      <Label>Modo de capacidad</Label>
                      <Select value={scaling} onValueChange={(value) => { setScaling(value); setGenerated(false); }}>
                        <SelectTrigger className="rounded-2xl">
                          <SelectValue />
                        </SelectTrigger>
                        <SelectContent>
                          <SelectItem value="reserved">Reserva garantizada</SelectItem>
                          <SelectItem value="burst">Reserva + burst</SelectItem>
                          <SelectItem value="shared">Compartido gestionado</SelectItem>
                        </SelectContent>
                      </Select>
                    </div>
                  </div>

                  <div className="grid gap-4 md:grid-cols-2">
                    <div className="flex items-center justify-between rounded-2xl border bg-white px-4 py-4">
                      <div>
                        <div className="font-medium">Ventana dedicada</div>
                        <div className="text-sm text-slate-600">Prioridad de servicio sobre backend reclaimable.</div>
                      </div>
                      <Switch checked={dedicatedWindow} onCheckedChange={(checked) => { setDedicatedWindow(checked); setGenerated(false); }} />
                    </div>
                    <div className="flex items-center justify-between rounded-2xl border bg-white px-4 py-4">
                      <div>
                        <div className="font-medium">Autenticación API Key</div>
                        <div className="text-sm text-slate-600">Protección del endpoint con credenciales de cliente.</div>
                      </div>
                      <Switch checked={apiKeyAuth} onCheckedChange={(checked) => { setApiKeyAuth(checked); setGenerated(false); }} />
                    </div>
                  </div>
                </TabsContent>

                <TabsContent value="network" className="space-y-6">
                  <div className="grid gap-4 md:grid-cols-2">
                    <div className="flex items-center justify-between rounded-2xl border bg-white px-4 py-4">
                      <div>
                        <div className="font-medium">Red privada</div>
                        <div className="text-sm text-slate-600">Usa un dominio privado interno para entornos corporativos.</div>
                      </div>
                      <Switch checked={privateNetwork} onCheckedChange={(checked) => { setPrivateNetwork(checked); setGenerated(false); }} />
                    </div>
                    <div className="rounded-2xl border bg-white p-4">
                      <div className="mb-2 flex items-center gap-2 font-medium">
                        <Globe className="h-4 w-4" />
                        Endpoint base
                      </div>
                      <p className="break-all text-sm text-slate-600">{endpointBase}</p>
                    </div>
                  </div>

                  <Alert className="rounded-2xl">
                    <KeyRound className="h-4 w-4" />
                    <AlertTitle>Provisionado seguro</AlertTitle>
                    <AlertDescription>
                      El frontend genera la configuración comercial y técnica del endpoint. El backend será quien cree la API key, namespace, límites y política de capacidad.
                    </AlertDescription>
                  </Alert>
                </TabsContent>
              </Tabs>

              <Separator className="my-6" />

              <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
                <div className="text-sm text-slate-600">
                  {canDeploy ? (
                    <span className="inline-flex items-center gap-2 text-emerald-700">
                      <CheckCircle2 className="h-4 w-4" />
                      La configuración es válida para el modelo seleccionado.
                    </span>
                  ) : (
                    <span className="text-rose-700">
                      Aumenta la VRAM al menos hasta {selectedModel.minVram} GB para desplegar este modelo.
                    </span>
                  )}
                </div>
                <Button className="rounded-2xl px-6" size="lg" disabled={!canDeploy} onClick={deploy}>
                  <Zap className="mr-2 h-4 w-4" />
                  Generar endpoint
                </Button>
              </div>
            </CardContent>
          </Card>

          <div className="space-y-6">
            <Card className="rounded-3xl border-0 shadow-lg">
              <CardHeader>
                <CardTitle>Servicio resultante</CardTitle>
                <CardDescription>Resumen técnico del despliegue que se ofrecería al cliente.</CardDescription>
              </CardHeader>
              <CardContent className="space-y-4">
                <div className="flex items-center gap-3 rounded-2xl bg-slate-100 p-4">
                  <div className="rounded-2xl bg-white p-3 shadow-sm">
                    <ServiceIcon className="h-5 w-5" />
                  </div>
                  <div>
                    <div className="font-medium text-slate-900">{serviceMeta.label}</div>
                    <div className="text-sm text-slate-600">{serviceMeta.color}</div>
                  </div>
                </div>

                <div className="grid gap-3 text-sm">
                  <div className="flex items-center justify-between rounded-xl border bg-white px-3 py-2">
                    <span className="text-slate-500">Tenant</span>
                    <span className="font-medium">{tenantName || "-"}</span>
                  </div>
                  <div className="flex items-center justify-between rounded-xl border bg-white px-3 py-2">
                    <span className="text-slate-500">Modelo</span>
                    <span className="font-medium">{selectedModel.name}</span>
                  </div>
                  <div className="flex items-center justify-between rounded-xl border bg-white px-3 py-2">
                    <span className="text-slate-500">VRAM</span>
                    <span className="font-medium">{vram[0]} GB</span>
                  </div>
                  <div className="flex items-center justify-between rounded-xl border bg-white px-3 py-2">
                    <span className="text-slate-500">Región</span>
                    <span className="font-medium">{region}</span>
                  </div>
                  <div className="flex items-center justify-between rounded-xl border bg-white px-3 py-2">
                    <span className="text-slate-500">Capacidad</span>
                    <span className="font-medium">{scaling}</span>
                  </div>
                </div>
              </CardContent>
            </Card>

            <Card className="rounded-3xl border-0 shadow-lg">
              <CardHeader>
                <CardTitle>Endpoint generado</CardTitle>
                <CardDescription>Vista previa del endpoint comercial y técnico que se provisionará.</CardDescription>
              </CardHeader>
              <CardContent className="space-y-4">
                <div className="rounded-2xl border bg-slate-50 p-4">
                  <div className="mb-2 flex items-center justify-between gap-3">
                    <div className="flex items-center gap-2 font-medium text-slate-900">
                      <ServerCog className="h-4 w-4" />
                      Endpoint HTTPS
                    </div>
                    <Button variant="outline" size="sm" className="rounded-xl" onClick={() => copyText(endpointBase)}>
                      <Copy className="mr-2 h-4 w-4" />
                      Copiar
                    </Button>
                  </div>
                  <div className="break-all text-sm text-slate-700">{endpointBase}</div>
                </div>

                <div className="rounded-2xl border bg-slate-50 p-4">
                  <div className="mb-2 flex items-center gap-2 font-medium text-slate-900">
                    <Cpu className="h-4 w-4" />
                    Ejemplo de consumo
                  </div>
                  <pre className="overflow-x-auto whitespace-pre-wrap rounded-xl bg-slate-900 p-4 text-xs leading-6 text-slate-100">
                    {sampleCurl}
                  </pre>
                </div>

                {generated ? (
                  <motion.div
                    initial={{ opacity: 0, y: 8 }}
                    animate={{ opacity: 1, y: 0 }}
                    className="rounded-2xl border border-emerald-200 bg-emerald-50 p-4"
                  >
                    <div className="flex items-start gap-3">
                      <CheckCircle2 className="mt-0.5 h-5 w-5 text-emerald-700" />
                      <div>
                        <div className="font-medium text-emerald-900">Configuración lista para provisionado</div>
                        <p className="mt-1 text-sm text-emerald-800">
                          El tenant <strong>{tenantName}</strong> quedaría aprovisionado con <strong>{vram[0]} GB</strong> para <strong>{serviceMeta.label.toLowerCase()}</strong> usando <strong>{selectedModel.name}</strong>.
                        </p>
                      </div>
                    </div>
                  </motion.div>
                ) : (
                  <div className="rounded-2xl border border-dashed p-4 text-sm text-slate-600">
                    Ajusta la configuración y pulsa <strong>Generar endpoint</strong> para ver la propuesta final del servicio.
                  </div>
                )}
              </CardContent>
            </Card>
          </div>
        </div>
      </div>
    </div>
  );
}
