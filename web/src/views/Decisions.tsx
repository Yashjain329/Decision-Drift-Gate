'use client';
// PORT TARGET: legacy/index.html section "decisions" + the matching render function in legacy/app.js.
import { View } from '@/components/Shell';
import { Empty, PageHead } from '@/components/ui';

export default function Decisions() {
  return (
    <View id="decisions" labelledBy="decisions-title">
      <PageHead id="decisions-title" crumb="Decisions" title="What the team agreed to" />
      <Empty glyph="decisions">Not ported yet.</Empty>
    </View>
  );
}
