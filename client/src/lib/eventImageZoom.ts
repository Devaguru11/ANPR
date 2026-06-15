import type { ImageZoomPayload } from "../components/ImageZoomDialog";
import type { ViolationEventRow } from "../components/ViolationEventCard";
import { receiverImageUrl } from "./receiverImageUrl";

type VehicleLike = {
  full_image_url?: string | null;
  plate_url?: string | null;
};

export function imageUrlsFromVehicleRow(row: VehicleLike) {
  const scene = receiverImageUrl(row.full_image_url);
  const plate = receiverImageUrl(row.plate_url);
  return { scene, plate };
}

export function zoomPayloadFromVehicleRow(row: VehicleLike): ImageZoomPayload | null {
  const { scene, plate } = imageUrlsFromVehicleRow(row);
  const src = scene || plate;
  if (!src) return null;
  return { src, sceneSrc: scene || undefined, plateSrc: plate || undefined };
}

export function imageUrlsFromViolationRow(row: ViolationEventRow) {
  const scene = receiverImageUrl(row.fullImageUrl);
  const plate = receiverImageUrl(row.plateUrl);
  return { scene, plate };
}

export function zoomPayloadFromViolationRow(row: ViolationEventRow): ImageZoomPayload | null {
  const { scene, plate } = imageUrlsFromViolationRow(row);
  const src = scene || plate;
  if (!src) return null;
  return { src, sceneSrc: scene || undefined, plateSrc: plate || undefined };
}
