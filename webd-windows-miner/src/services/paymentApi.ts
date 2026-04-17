import type { WebdPaymentRequest, WebdPaymentResult } from '../types/miner'
import { sendDesktopTransaction } from './desktopApi'

export async function sendPaymentTransaction(request: WebdPaymentRequest): Promise<WebdPaymentResult> {
  return sendDesktopTransaction(request)
}
