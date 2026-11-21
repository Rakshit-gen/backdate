import { Hero } from "@/components/Hero";
import { SceneProvider } from "@/components/SceneProvider";
import { SourceNote } from "@/components/SourceNote";
import { getSource } from "@/lib/source";

export const dynamic = "force-dynamic";

export default async function Page() {
  const source = await getSource();
  return (
    <SceneProvider source={source}>
      <SourceNote />
      <Hero />
    </SceneProvider>
  );
}
