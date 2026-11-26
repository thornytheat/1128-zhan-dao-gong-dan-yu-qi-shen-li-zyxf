function drawProjectChart(target, points) {
    const register = named('dl',undefined,'permit-register');
    const sorted = [...points].sort((left,right)=>right.value-left.value);
    for (const row of sorted) {
        const block = named('div',undefined,'permit-stamp');
        block.append(named('dt',row.label),named('dd',row.value));
        register.append(block);
    }
    target.append(register);
}
