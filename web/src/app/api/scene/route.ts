import { BackendError, loadScene } from "@/lib/source";

export const dynamic = "force-dynamic";

export async function GET(req: Request) {
  const employee = Number(new URL(req.url).searchParams.get("employee") ?? NaN);
  try {
    return Response.json(await loadScene(Number.isInteger(employee) ? employee : undefined));
  } catch (e) {
    const status = e instanceof BackendError ? 502 : 500;
    return Response.json({ error: (e as Error).message }, { status });
  }
}
