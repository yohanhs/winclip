"use client";

import { useEffect, useState } from "react";
import { Loader2 } from "lucide-react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { useUpdateClip } from "@/hooks/use-clips";
import { errorMessage } from "@/lib/api";
import type { ClipOut } from "@winclip/api-client";

export interface ClipEditDialogProps {
  clip: ClipOut | null;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

export function ClipEditDialog({
  clip,
  open,
  onOpenChange,
}: ClipEditDialogProps) {
  const [title, setTitle] = useState("");
  const [description, setDescription] = useState("");
  const [hashtags, setHashtags] = useState("");
  const updateClip = useUpdateClip(clip?.project_id);

  useEffect(() => {
    if (!clip) return;
    setTitle(clip.title);
    setDescription(clip.description);
    setHashtags(clip.hashtags.join(" "));
  }, [clip]);

  const handleSave = () => {
    if (!clip) return;
    if (title.trim().length === 0) {
      toast.error("El título no puede estar vacío.");
      return;
    }

    const parsedTags = hashtags
      .split(/[\s,]+/)
      .map((tag) => tag.trim().replace(/^#+/, ""))
      .filter((tag) => tag.length > 0);

    updateClip.mutate(
      {
        clipId: clip.id,
        data: {
          title: title.trim(),
          description: description.trim(),
          hashtags: parsedTags,
        },
      },
      {
        onSuccess: () => {
          toast.success("Clip actualizado");
          onOpenChange(false);
        },
        onError: (error) => {
          toast.error("No se pudo actualizar el clip", {
            description: errorMessage(error),
          });
        },
      },
    );
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Editar clip</DialogTitle>
          <DialogDescription>
            Ajusta el título, la descripción y los hashtags que se publicarán.
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-4">
          <div className="space-y-2">
            <Label htmlFor="clip-title">Título</Label>
            <Input
              id="clip-title"
              value={title}
              onChange={(event) => setTitle(event.target.value)}
              disabled={updateClip.isPending}
            />
          </div>

          <div className="space-y-2">
            <Label htmlFor="clip-description">Descripción</Label>
            <Textarea
              id="clip-description"
              rows={4}
              value={description}
              onChange={(event) => setDescription(event.target.value)}
              disabled={updateClip.isPending}
            />
          </div>

          <div className="space-y-2">
            <Label htmlFor="clip-hashtags">Hashtags</Label>
            <Input
              id="clip-hashtags"
              value={hashtags}
              onChange={(event) => setHashtags(event.target.value)}
              placeholder="#shorts #finanzas #ahorro"
              disabled={updateClip.isPending}
            />
            <p className="text-xs text-zinc-500">
              Sepáralos con espacios o comas. La almohadilla es opcional.
            </p>
          </div>
        </div>

        <DialogFooter>
          <Button
            type="button"
            variant="ghost"
            onClick={() => onOpenChange(false)}
            disabled={updateClip.isPending}
          >
            Cancelar
          </Button>
          <Button
            type="button"
            onClick={handleSave}
            disabled={updateClip.isPending}
          >
            {updateClip.isPending ? (
              <>
                <Loader2 className="animate-spin" aria-hidden="true" />
                Guardando…
              </>
            ) : (
              "Guardar cambios"
            )}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
