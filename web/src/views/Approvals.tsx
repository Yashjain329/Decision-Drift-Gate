'use client';
// PORT TARGET: legacy/index.html section "approvals" + the matching render function in legacy/app.js.
import { View } from '@/components/Shell';
import { Empty, PageHead } from '@/components/ui';

export default function Approvals() {
  return (
    <View id="approvals" labelledBy="approvals-title">
      <PageHead id="approvals-title" crumb="Approvals" title="Who authorized this exact check?" />
      <Empty glyph="approvals">Not ported yet.</Empty>
    </View>
  );
}
