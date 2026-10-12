'use client';
// PORT TARGET: legacy/index.html section "reports" + the matching render function in legacy/app.js.
import { View } from '@/components/Shell';
import { Empty, PageHead } from '@/components/ui';

export default function Reports() {
  return (
    <View id="reports" labelledBy="reports-title">
      <PageHead id="reports-title" crumb="Reports" title="Audit report" />
      <Empty glyph="reports">Not ported yet.</Empty>
    </View>
  );
}
